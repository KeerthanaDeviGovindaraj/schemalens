"""Unit tests for the dependency analyzer. No database needed.

Day 1 (task 1.3): make every test here pass. They encode the labeling
semantics in design.md section 2, so fix the analyzer, not the tests.
"""

from __future__ import annotations

from schemalens.analyzer import TableRef, analyze_routine, analyze_sql
from schemalens.analyzer.resolve import resolve


def T(qualified: str) -> TableRef:
    if "." in qualified:
        schema, name = qualified.split(".", 1)
        return TableRef(schema, name)
    return TableRef(None, qualified)


def refs(*names: str) -> set[TableRef]:
    return {T(n) for n in names}


# ---------------------------------------------------------------- plain SQL


def test_select_join_reads_both_tables():
    d = analyze_sql("SELECT * FROM public.film f JOIN inventory i USING (film_id)")
    assert d.reads == refs("public.film", "inventory")
    assert d.writes == set()


def test_cte_name_is_not_a_table():
    d = analyze_sql("WITH x AS (SELECT * FROM public.rental) SELECT * FROM x")
    assert d.reads == refs("public.rental")


def test_schema_qualified_table_named_like_cte_is_still_a_table():
    d = analyze_sql("WITH film AS (SELECT 1) SELECT * FROM public.film, film")
    assert d.reads == refs("public.film")


def test_insert_select():
    d = analyze_sql("INSERT INTO public.a (x) SELECT x FROM public.b")
    assert d.writes == refs("public.a")
    assert d.reads == refs("public.b")


def test_update_from_target_is_write_only():
    d = analyze_sql(
        "UPDATE public.payment p SET amount = 0 FROM public.rental r WHERE r.rental_id = p.rental_id"
    )
    assert d.writes == refs("public.payment")
    assert d.reads == refs("public.rental")


def test_delete_using_and_subquery():
    d = analyze_sql(
        "DELETE FROM public.a USING public.b WHERE a.id = b.id AND a.k IN (SELECT k FROM public.c)"
    )
    assert d.writes == refs("public.a")
    assert d.reads == refs("public.b", "public.c")


def test_explicit_self_reference_in_subquery_is_a_read():
    d = analyze_sql("UPDATE public.a SET v = (SELECT max(v) FROM public.a)")
    assert d.writes == refs("public.a")
    assert d.reads == refs("public.a")


def test_writable_cte():
    d = analyze_sql(
        "WITH moved AS (DELETE FROM public.rental RETURNING *) "
        "INSERT INTO bench.rental_archive SELECT * FROM moved"
    )
    assert d.writes == refs("public.rental", "bench.rental_archive")
    assert d.reads == set()


def test_truncate():
    d = analyze_sql("TRUNCATE public.a, public.b")
    assert d.writes == refs("public.a", "public.b")
    assert d.reads == set()


def test_merge():
    d = analyze_sql(
        "MERGE INTO public.t USING public.s ON t.id = s.id "
        "WHEN MATCHED THEN UPDATE SET v = s.v "
        "WHEN NOT MATCHED THEN INSERT (id, v) VALUES (s.id, s.v)"
    )
    assert d.writes == refs("public.t")
    assert d.reads == refs("public.s")


def test_plpgsql_condition_fragment():
    d = analyze_sql("EXISTS (SELECT 1 FROM public.customer WHERE email = 'x')")
    assert d.reads == refs("public.customer")
    assert d.flags == []


def test_assignment_fragment():
    d = analyze_sql("v := (SELECT count(*) FROM public.film)")
    assert d.reads == refs("public.film")
    assert d.flags == []


def test_garbage_becomes_parse_error_flag():
    d = analyze_sql("this is ((( not sql")
    assert [f.kind for f in d.flags] == ["parse_error"]


# ---------------------------------------------------------------- routines


PLPGSQL_DYNAMIC = """
CREATE OR REPLACE FUNCTION bench.refresh_store_stats()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
  EXECUTE format('TRUNCATE %I.%I', 'bench', 'store_stats');
  INSERT INTO bench.store_stats (store_id, customers)
  SELECT store_id, count(*) FROM public.customer GROUP BY store_id;
END;
$function$
"""

PLPGSQL_IF_EXISTS = """
CREATE OR REPLACE FUNCTION bench.customer_exists(p_email text)
 RETURNS boolean
 LANGUAGE plpgsql
AS $function$
BEGIN
  IF EXISTS (SELECT 1 FROM public.customer WHERE email = p_email) THEN
    RETURN true;
  END IF;
  RETURN false;
END;
$function$
"""

PLPGSQL_TRIGGER = """
CREATE OR REPLACE FUNCTION bench.touch_last_update()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
  NEW.last_update := now();
  RETURN NEW;
END;
$function$
"""

PLPGSQL_SELECT_INTO = """
CREATE OR REPLACE FUNCTION bench.film_title(p_film_id integer)
 RETURNS text
 LANGUAGE plpgsql
AS $function$
DECLARE
  v_title text;
BEGIN
  SELECT title INTO v_title FROM film WHERE film_id = p_film_id;
  RETURN v_title;
END;
$function$
"""

PLPGSQL_RETURN_QUERY_CTE = """
CREATE OR REPLACE FUNCTION bench.cte_top_films(p_limit integer)
 RETURNS TABLE(title text, rentals bigint)
 LANGUAGE plpgsql
AS $function$
BEGIN
  RETURN QUERY
  WITH counts AS (
    SELECT i.film_id, count(*) AS n
    FROM public.rental r JOIN public.inventory i ON i.inventory_id = r.inventory_id
    GROUP BY i.film_id
  )
  SELECT f.title::text, c.n FROM counts c JOIN public.film f ON f.film_id = c.film_id
  ORDER BY c.n DESC LIMIT p_limit;
END;
$function$
"""


def test_dynamic_sql_is_flagged_and_static_sql_still_analyzed():
    d = analyze_routine(PLPGSQL_DYNAMIC, "plpgsql")
    assert "dynamic_sql" in {f.kind for f in d.flags}
    assert d.writes == refs("bench.store_stats")
    assert d.reads == refs("public.customer")


def test_if_exists_condition():
    d = analyze_routine(PLPGSQL_IF_EXISTS, "plpgsql")
    assert d.reads == refs("public.customer")
    assert d.writes == set()
    assert d.flags == []


def test_trigger_function_has_no_deps_and_no_errors():
    d = analyze_routine(PLPGSQL_TRIGGER, "plpgsql")
    assert d.reads == set()
    assert d.writes == set()
    assert d.flags == []


def test_select_into_variable_is_not_a_write():
    d = analyze_routine(PLPGSQL_SELECT_INTO, "plpgsql")
    assert d.reads == refs("film")
    assert d.writes == set()


def test_return_query_with_cte():
    d = analyze_routine(PLPGSQL_RETURN_QUERY_CTE, "plpgsql")
    assert d.reads == refs("public.rental", "public.inventory", "public.film")


def test_sql_language_uses_body():
    body = (
        "SELECT count(*) FROM public.rental r "
        "JOIN public.inventory i USING (inventory_id) WHERE i.film_id = $1"
    )
    d = analyze_routine("CREATE FUNCTION ignored() ...", "sql", body)
    assert d.reads == refs("public.rental", "public.inventory")


def test_unsupported_language_never_raises():
    d = analyze_routine("whatever", "plpython3u")
    assert [f.kind for f in d.flags] == ["parse_error"]


# ---------------------------------------------------------------- resolver


def test_resolver():
    known = {"public.film", "bench.store_stats"}
    assert resolve(T("film"), known) == "public.film"
    assert resolve(T("public.film"), known) == "public.film"
    assert resolve(T("store_stats"), known) is None
    assert resolve(T("store_stats"), known, ["bench", "public"]) == "bench.store_stats"
    assert resolve(T("tmp_x"), known) is None
