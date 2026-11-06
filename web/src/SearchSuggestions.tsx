import { useId, useState } from "react";

export default function SearchSuggestions({ value, onChange, options, onSelect, label, placeholder } : {
  value: string; onChange: (value: string) => void;
  options: { id: string; name: string; detail: string; search?: string }[];
  onSelect: (id: string) => void; label: string; placeholder?: string;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const matches = options.filter(x => `${x.name} ${x.detail} ${x.search || ""}`.toLowerCase().includes(value.trim().toLowerCase())).slice(0, 10);
  function choose(index: number) {
    if (!matches[index]) return;
    onChange(matches[index].id);
    onSelect(matches[index].id);
    setOpen(false);
  }
  return <div className="suggestion-field">
    <input aria-label={label} role="combobox" autoComplete="off" placeholder={placeholder || "Name or ID"}
      value={value} aria-expanded={open && !!value.trim()} aria-controls={id}
      aria-activedescendant={open && matches[active] ? `${id}-${active}` : undefined}
      onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
      onChange={e => { onChange(e.target.value); setActive(0); setOpen(true); }}
      onKeyDown={e => {
        if (e.key === "Escape") setOpen(false);
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault(); setOpen(true);
          setActive(n => Math.max(0, Math.min(matches.length - 1, n + (e.key === "ArrowDown" ? 1 : -1))));
        }
        if (e.key === "Enter" && open && value.trim() && matches.length) { e.preventDefault(); choose(active); }
      }} />
    {open && !!value.trim() && <div className="suggestion-list" id={id} role="listbox">
      {matches.map((x, i) => <button type="button" role="option" aria-selected={i === active}
        id={`${id}-${i}`} key={x.id} onMouseDown={e => e.preventDefault()} onClick={() => choose(i)}>
        <strong>{x.name}</strong><small>{x.detail}</small>
      </button>)}
      {!matches.length && <p role="status">Searching for matches. Use the selector below when results arrive.</p>}
    </div>}
  </div>;
}
