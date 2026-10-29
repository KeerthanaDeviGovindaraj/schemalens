-- Benchmark fixtures: tricky patterns for the dependency analyzer.
-- Loaded after Pagila (01-, 02- files from scripts/get_pagila.sh).
-- Every function here needs a matching entry in benchmark/labels.yaml.
-- Task 4.2: add 30-40 more, one pattern per function.

CREATE SCHEMA IF NOT EXISTS bench;

CREATE TABLE bench.rental_archive (LIKE public.rental);

CREATE TABLE bench.store_stats (
  store_id    integer PRIMARY KEY,
  customers   bigint NOT NULL,
  last_update timestamptz NOT NULL DEFAULT now()
);

-- 1. Read-only CTE inside RETURN QUERY. "counts" must not appear as a table.
CREATE FUNCTION bench.cte_top_films(p_limit integer)
RETURNS TABLE (title text, rentals bigint)
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  WITH counts AS (
    SELECT i.film_id, count(*) AS n
    FROM public.rental r
    JOIN public.inventory i ON i.inventory_id = r.inventory_id
    GROUP BY i.film_id
  )
  SELECT f.title::text, c.n
  FROM counts c
  JOIN public.film f ON f.film_id = c.film_id
  ORDER BY c.n DESC
  LIMIT p_limit;
END;
$$;

-- 2. Writable CTE: DELETE inside WITH, INSERT reading from the CTE.
CREATE FUNCTION bench.archive_old_rentals(p_before timestamptz)
RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
  v_count integer;
BEGIN
  WITH moved AS (
    DELETE FROM public.rental
    WHERE return_date < p_before
    RETURNING *
  )
  INSERT INTO bench.rental_archive
  SELECT * FROM moved;
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$;

-- 3. UPDATE ... FROM: one write target, one read.
CREATE FUNCTION bench.apply_late_fees(p_fee numeric)
RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  UPDATE public.payment p
  SET amount = p.amount + p_fee
  FROM public.rental r
  WHERE r.rental_id = p.rental_id
    AND r.return_date IS NULL;
END;
$$;

-- 4. Dynamic SQL (flagged) next to static SQL (still analyzed).
CREATE FUNCTION bench.refresh_store_stats()
RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  EXECUTE format('TRUNCATE %I.%I', 'bench', 'store_stats');
  INSERT INTO bench.store_stats (store_id, customers)
  SELECT store_id, count(*)
  FROM public.customer
  GROUP BY store_id;
END;
$$;

-- 5. Table reference inside an IF condition (a fragment, not a statement).
CREATE FUNCTION bench.customer_exists(p_email text)
RETURNS boolean
LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM public.customer WHERE email = p_email) THEN
    RETURN true;
  END IF;
  RETURN false;
END;
$$;

-- 6. Trigger function with an assignment and no table references.
CREATE FUNCTION bench.touch_last_update()
RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.last_update := now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER store_stats_touch
BEFORE UPDATE ON bench.store_stats
FOR EACH ROW EXECUTE FUNCTION bench.touch_last_update();

-- 7. SQL-language function (parsed with the SQL parser, not PL/pgSQL).
CREATE FUNCTION bench.rentals_for_film(integer)
RETURNS bigint
LANGUAGE sql STABLE AS $$
  SELECT count(*)
  FROM public.rental r
  JOIN public.inventory i ON i.inventory_id = r.inventory_id
  WHERE i.film_id = $1;
$$;

-- 8. Unqualified table name + SELECT INTO a variable (resolved via search path).
CREATE FUNCTION bench.film_title(p_film_id integer)
RETURNS text
LANGUAGE plpgsql AS $$
DECLARE
  v_title text;
BEGIN
  SELECT title INTO v_title FROM film WHERE film_id = p_film_id;
  RETURN v_title;
END;
$$;
