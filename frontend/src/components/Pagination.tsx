import { ChevronLeft, ChevronRight } from "lucide-react";

export function Pagination({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  const first = total === 0 ? 0 : offset + 1;
  const last = Math.min(offset + limit, total);
  return (
    <div className="pagination">
      <span>
        {first}–{last} of {total}
      </span>
      <div>
        <button
          className="icon-button"
          type="button"
          aria-label="Previous page"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          <ChevronLeft size={17} />
        </button>
        <button
          className="icon-button"
          type="button"
          aria-label="Next page"
          disabled={offset + limit >= total}
          onClick={() => onChange(offset + limit)}
        >
          <ChevronRight size={17} />
        </button>
      </div>
    </div>
  );
}
