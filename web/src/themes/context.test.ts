// @vitest-environment jsdom

import { afterEach, describe, expect, it } from "vitest";
import { defaultTheme } from "./presets";
import { applyTheme, persistThemeChoice } from "./context";

describe("contributed dashboard themes", () => {
  afterEach(() => {
    document.head.innerHTML = "";
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.removeAttribute("style");
  });

  it("applies custom properties through data-theme and persists the choice", () => {
    const pluginCSS = document.createElement("style");
    pluginCSS.textContent = `
      :root[data-theme="test-contributed"] {
        --color-primary: #4F6AF5;
        --color-border: #E5E7EB;
      }
    `;
    document.head.appendChild(pluginCSS);

    applyTheme(defaultTheme, {
      name: "test-contributed",
      stylesheet: "/dashboard-plugins/test/theme.css",
    });
    persistThemeChoice("test-contributed");

    const root = document.documentElement;
    const computed = getComputedStyle(root);
    expect(root.dataset.theme).toBe("test-contributed");
    expect(computed.getPropertyValue("--color-primary").trim()).toBe("#4F6AF5");
    expect(computed.getPropertyValue("--color-border").trim()).toBe("#E5E7EB");
    expect(localStorage.getItem("hermes-dashboard-theme")).toBe("test-contributed");
    expect(
      document.querySelector<HTMLLinkElement>("link[data-hermes-theme-stylesheet]")
        ?.getAttribute("href"),
    ).toBe("/dashboard-plugins/test/theme.css");
  });
});
