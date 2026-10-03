// Botón para pasar del tema claro al oscuro y volver. El nombre accesible dice lo que hará al pulsarlo.
import Icon from "./Icon";
import { T } from "../lib/i18n";
import { useSession } from "../lib/session";
import { useTheme } from "../lib/theme";

export default function ThemeToggle() {
  const { lang } = useSession();
  const { theme, toggle } = useTheme();
  const label = theme === "dark" ? T[lang].themeToLight : T[lang].themeToDark;
  return (
    <button type="button" className="theme-toggle" onClick={toggle} aria-label={label} title={label}>
      <Icon name={theme === "dark" ? "sun" : "moon"} />
    </button>
  );
}
