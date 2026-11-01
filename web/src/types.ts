// Mirrors schemalens/bundle.py. Keep in sync with the Pydantic models.

export interface Column {
  name: string;
  data_type: string;
  nullable: boolean;
  is_pk: boolean;
  default_expr: string | null;
  comment: string | null;
}

export interface ForeignKey {
  name: string;
  from_cols: string[];
  to_relation: string;
  to_cols: string[];
}

export interface Relation {
  id: string;
  schema: string;
  name: string;
  kind: "table" | "view" | "matview";
  comment: string | null;
  columns: Column[];
  foreign_keys: ForeignKey[];
}

export interface Flag {
  kind: string;
  detail: string;
}

export interface Parameter {
  name: string;
  meaning: string;
}

export interface Explanation {
  summary: string;
  purpose: string;
  parameters: Parameter[];
  reads: string[];
  writes: string[];
  side_effects: string[];
  caveats: string[];
  disagreements: string[];
}

export interface Routine {
  id: string;
  schema: string;
  name: string;
  args: string;
  returns: string | null;
  kind: "function" | "procedure";
  language: "plpgsql" | "sql";
  definition: string;
  reads: string[];
  writes: string[];
  flags: Flag[];
  explanation: Explanation | null;
}

export interface Trigger {
  name: string;
  relation_id: string;
  routine_id: string | null;
}

export interface Meta {
  db_name: string | null;
  scanned_at: string | null;
  server_version: string | null;
  schemalens_version: string | null;
  search_path: string | null;
}

export interface Bundle {
  meta: Meta;
  relations: Relation[];
  routines: Routine[];
  triggers: Trigger[];
}
