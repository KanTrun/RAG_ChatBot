const STATUS_GUIDE = [
  {
    label: "Pending",
    description: "File was accepted and queued for indexing.",
  },
  {
    label: "Processing",
    description: "The system is parsing, chunking, and embedding the document.",
  },
  {
    label: "Indexed",
    description: "The document is searchable and chat can answer from it.",
  },
  {
    label: "Failed",
    description: "Indexing failed. Re-index the file or upload it again.",
  },
];

export function DocumentIndexingGuide() {
  return (
    <div className="rounded-2xl border border-border-primary bg-surface-secondary/80 p-4">
      <h3 className="text-sm font-semibold text-content-primary">How indexing works</h3>
      <p className="mt-2 text-sm leading-6 text-content-secondary">
        Users can upload and re-index their own documents. Admins can manage every
        document in the system, but admin permission is not required for a user to
        index their own files.
      </p>
      <ul className="mt-4 grid gap-3 sm:grid-cols-2">
        {STATUS_GUIDE.map((item) => (
          <li
            key={item.label}
            className="rounded-xl border border-white/5 bg-black/10 px-3 py-3"
          >
            <p className="text-sm font-medium text-content-primary">{item.label}</p>
            <p className="mt-1 text-xs leading-5 text-content-tertiary">
              {item.description}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
