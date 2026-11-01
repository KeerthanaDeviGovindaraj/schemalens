import { Link } from "react-router-dom";

export function Breadcrumb({ current }: { current: string }) {
  return (
    <nav className="breadcrumb" aria-label="Breadcrumb">
      <Link to="/">Search</Link>
      <span className="sep" aria-hidden="true">
        /
      </span>
      <span className="crumb-current">{current}</span>
    </nav>
  );
}
