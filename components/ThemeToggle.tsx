"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";
const STORAGE_KEY = "invest-system-theme";

function readTheme(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const apply = (next: Theme) => {
      setTheme(next);
      document.documentElement.dataset.theme = next;
      window.dispatchEvent(new Event("invest-system-theme-change"));
    };
    apply(readTheme());
    const onStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) apply(event.newValue === "dark" ? "dark" : "light");
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    try { localStorage.setItem(STORAGE_KEY, next); } catch { /* theme still works for this page */ }
    document.documentElement.dataset.theme = next;
    setTheme(next);
    window.dispatchEvent(new Event("invest-system-theme-change"));
  }

  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label={`Chuyển sang giao diện ${theme === "dark" ? "sáng" : "tối"}`}
      aria-pressed={theme === "dark"}
      onClick={toggle}
    >
      {theme === "dark" ? (
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" />
        </svg>
      ) : (
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M20.2 15.1A8.5 8.5 0 0 1 8.9 3.8 8.5 8.5 0 1 0 20.2 15.1Z" />
        </svg>
      )}
      <span>{theme === "dark" ? "Tối" : "Sáng"}</span>
    </button>
  );
}
