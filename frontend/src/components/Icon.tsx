// Iconos de la navegación (trazo simple, 24 px). Decorativos: el texto del enlace es el nombre accesible.
const PATHS: Record<string, string> = {
  chat: "M4 5h16v11H9l-5 4z",
  history: "M12 7v5l3 2M4.5 12a7.5 7.5 0 1 0 2.2-5.3M4 4v4h4",
  list: "M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01",
  flag: "M5 21V4m0 1h11l-2 4 2 4H5",
  ticket: "M4 8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4zM14 6v12",
  gauge: "M4 18a8 8 0 1 1 16 0M12 18l4-6",
};

export type IconName = keyof typeof PATHS;

export default function Icon({ name }: { name: IconName }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={PATHS[name]} />
    </svg>
  );
}
