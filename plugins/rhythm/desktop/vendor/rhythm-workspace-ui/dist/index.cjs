'use strict';

var react = require('react');
var jsxRuntime = require('react/jsx-runtime');
var Icons = require('lucide-react');

function _interopNamespace(e) {
  if (e && e.__esModule) return e;
  var n = Object.create(null);
  if (e) {
    Object.keys(e).forEach(function (k) {
      if (k !== 'default') {
        var d = Object.getOwnPropertyDescriptor(e, k);
        Object.defineProperty(n, k, d.get ? d : {
          enumerable: true,
          get: function () { return e[k]; }
        });
      }
    });
  }
  n.default = e;
  return Object.freeze(n);
}

var Icons__namespace = /*#__PURE__*/_interopNamespace(Icons);

// src/context.tsx
var DomainGatewayContext = react.createContext(null);
var HostAdapterContext = react.createContext(null);
function RhythmWorkspaceProvider({ gateway, host, children }) {
  return /* @__PURE__ */ jsxRuntime.jsx(DomainGatewayContext.Provider, { value: gateway, children: /* @__PURE__ */ jsxRuntime.jsx(HostAdapterContext.Provider, { value: host, children }) });
}
function useRhythmDomainGateway() {
  const gateway = react.useContext(DomainGatewayContext);
  if (!gateway) throw new Error("useRhythmDomainGateway must be used within RhythmWorkspaceProvider");
  return gateway;
}
function useRhythmHost() {
  const host = react.useContext(HostAdapterContext);
  if (!host) throw new Error("useRhythmHost must be used within RhythmWorkspaceProvider");
  return host;
}

// src/host/theme.ts
var RHYTHM_ROOT_CLASS = "rhythm-workspace-root";
var defaultRhythmTokens = {
  mode: "dark",
  bg: "#171a1b",
  surface: "#1f2426",
  surfaceWarm: "#283230",
  surfaceRaised: "#262d2f",
  fg: "#f3f6f5",
  fgSecondary: "#c7d6d3",
  fgMuted: "#9fb0ad",
  border: "#4d6260",
  borderSoft: "#33403e",
  accent: "#4fb8a0",
  accentOn: "#0c1716",
  accentHover: "#469e8a",
  success: "#5fbf83",
  warning: "#d1a24f",
  danger: "#d1584a",
  info: "#5a9fd1",
  fontUi: "Inter, system-ui, sans-serif",
  fontMono: '"SF Mono", ui-monospace, Menlo, monospace',
  radiusSm: "10px",
  radiusMd: "16px",
  radiusLg: "24px",
  radiusPill: "999px",
  focusRing: "0 0 0 4px rgba(79, 184, 160, 0.32)",
  shadow: "0 24px 80px rgba(10, 14, 13, 0.4)"
};
function mapHostTokens(tokens) {
  const merged = { ...defaultRhythmTokens, ...tokens };
  return {
    "--rhythm-bg": merged.bg,
    "--rhythm-surface": merged.surface,
    "--rhythm-surface-warm": merged.surfaceWarm,
    "--rhythm-surface-raised": merged.surfaceRaised,
    "--rhythm-fg": merged.fg,
    "--rhythm-fg-secondary": merged.fgSecondary,
    "--rhythm-fg-muted": merged.fgMuted,
    "--rhythm-border": merged.border,
    "--rhythm-border-soft": merged.borderSoft,
    "--rhythm-accent": merged.accent,
    "--rhythm-accent-on": merged.accentOn,
    "--rhythm-accent-hover": merged.accentHover,
    "--rhythm-success": merged.success,
    "--rhythm-warning": merged.warning,
    "--rhythm-danger": merged.danger,
    "--rhythm-info": merged.info,
    "--rhythm-font-ui": merged.fontUi,
    "--rhythm-font-mono": merged.fontMono,
    "--rhythm-radius-sm": merged.radiusSm,
    "--rhythm-radius-md": merged.radiusMd,
    "--rhythm-radius-lg": merged.radiusLg,
    "--rhythm-radius-pill": merged.radiusPill,
    "--rhythm-focus": merged.focusRing,
    "--rhythm-shadow": merged.shadow
  };
}

// src/domain/types.ts
var RhythmGatewayError = class extends Error {
  constructor(kind, message) {
    super(message);
    this.kind = kind;
  }
  kind;
};
function ScreenRoot({ screenName, testId, children, extraDataAttributes }) {
  const host = useRhythmHost();
  return /* @__PURE__ */ jsxRuntime.jsx(
    "main",
    {
      className: RHYTHM_ROOT_CLASS,
      "aria-label": screenName,
      "data-testid": testId,
      "data-rhythm-viewport": host.viewport,
      "data-rhythm-theme": host.tokens.mode,
      style: mapHostTokens(host.tokens),
      ...extraDataAttributes,
      children
    }
  );
}
var CAPABILITIES = ["state.get", "state.update", "pco.services.read"];
var MAX_BRIDGE_PAYLOAD_BYTES = 1024 * 1024;
function inline(value, closingTag) {
  return value.replace(new RegExp(`</${closingTag}`, "gi"), `<\\/${closingTag}`);
}
function documentSource(document2, nonce) {
  const csp = `default-src 'none'; base-uri 'none'; connect-src 'none'; form-action 'none'; frame-src 'none'; img-src 'none'; media-src 'none'; font-src 'none'; object-src 'none'; worker-src 'none'; manifest-src 'none'; navigate-to 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}'`;
  return `<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${csp}"><style nonce="${nonce}">${inline(document2.styleText, "style")}</style>${document2.bodyHtml}<script nonce="${nonce}">${inline(document2.scriptText, "script")}</script>`;
}
function isCapabilityMessage(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const message = value;
  return message.type === "rhythm-artifact-capability" && ["requestId", "frameId", "artifactId", "sessionId", "bundleGeneration", "stateGeneration"].every((key) => typeof message[key] === "string" && message[key].length > 0) && typeof message.capability === "string" && CAPABILITIES.includes(message.capability) && isBoundedJson(message.payload);
}
function isBoundedJson(value) {
  try {
    return new TextEncoder().encode(JSON.stringify(value)).byteLength <= MAX_BRIDGE_PAYLOAD_BYTES;
  } catch {
    return false;
  }
}
function documentIsBound(document2, artifactId) {
  return document2.artifactId === artifactId && [document2.sessionId, document2.bundleGeneration, document2.stateGeneration].every((value) => value.length > 0) && document2.capabilities.every((capability) => CAPABILITIES.includes(capability));
}
function createNonce() {
  if (!globalThis.crypto?.getRandomValues) return null;
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}
function ArtifactsScreen({ artifactsGateway, artifactHostPort }) {
  const [items, setItems] = react.useState([]);
  const [opened, setOpened] = react.useState(null);
  const [frameId, setFrameId] = react.useState("");
  const [nonce, setNonce] = react.useState("");
  const frame = react.useRef(null);
  const nextFrameId = react.useRef(0);
  const openAttempt = react.useRef(0);
  const seenRequestIds = react.useRef(/* @__PURE__ */ new Set());
  react.useEffect(() => {
    if (!artifactsGateway) return;
    let cancelled = false;
    void artifactsGateway.list().then((loaded) => {
      if (!cancelled) setItems(loaded);
    });
    return () => {
      cancelled = true;
    };
  }, [artifactsGateway]);
  react.useEffect(() => {
    if (!opened || !artifactHostPort || !frameId) return;
    const onMessage = (event) => {
      const message = event.data;
      if (!isCapabilityMessage(message) || event.origin !== "null" || event.source !== frame.current?.contentWindow) return;
      if (message.frameId !== frameId || message.artifactId !== opened.artifactId || message.sessionId !== opened.sessionId || message.bundleGeneration !== opened.bundleGeneration || message.stateGeneration !== opened.stateGeneration || !opened.capabilities.includes(message.capability) || seenRequestIds.current.has(message.requestId)) return;
      seenRequestIds.current.add(message.requestId);
      const source = event.source;
      if (!source) return;
      void artifactHostPort.receive(message).then((result) => {
        if (source === frame.current?.contentWindow) {
          source.postMessage({ type: "rhythm-artifact-capability-result", requestId: message.requestId, frameId, artifactId: opened.artifactId, sessionId: opened.sessionId, bundleGeneration: opened.bundleGeneration, stateGeneration: opened.stateGeneration, ...result }, "*");
        }
      }).catch(() => {
        if (source === frame.current?.contentWindow) {
          source.postMessage({ type: "rhythm-artifact-capability-result", requestId: message.requestId, frameId, artifactId: opened.artifactId, sessionId: opened.sessionId, bundleGeneration: opened.bundleGeneration, stateGeneration: opened.stateGeneration, status: "error" }, "*");
        }
      });
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [artifactHostPort, frameId, opened]);
  const openArtifact = (artifactId) => {
    if (!artifactHostPort) return;
    const attempt = ++openAttempt.current;
    void artifactHostPort.open(artifactId).then((document2) => {
      const nextNonce = createNonce();
      if (attempt !== openAttempt.current || !nextNonce || !documentIsBound(document2, artifactId)) return;
      nextFrameId.current += 1;
      seenRequestIds.current.clear();
      setFrameId(`rhythm-artifact-frame-${nextFrameId.current}`);
      setNonce(nextNonce);
      setOpened(document2);
    });
  };
  return /* @__PURE__ */ jsxRuntime.jsxs(
    ScreenRoot,
    {
      screenName: "Artifacts",
      testId: "rhythm-artifacts-screen",
      extraDataAttributes: { "data-rhythm-artifacts-state": artifactsGateway ? "unlocked" : "locked" },
      children: [
        /* @__PURE__ */ jsxRuntime.jsx("h1", { children: "Artifacts" }),
        artifactsGateway ? /* @__PURE__ */ jsxRuntime.jsxs(jsxRuntime.Fragment, { children: [
          /* @__PURE__ */ jsxRuntime.jsx("ul", { "data-testid": "rhythm-artifacts-list", children: items.map((artifact) => /* @__PURE__ */ jsxRuntime.jsx("li", { "data-testid": `rhythm-artifact-row-${artifact.id}`, children: artifactHostPort ? /* @__PURE__ */ jsxRuntime.jsx("button", { type: "button", onClick: () => openArtifact(artifact.id), "data-testid": `rhythm-artifact-open-${artifact.id}`, children: artifact.title }) : artifact.title }, artifact.id)) }),
          opened && frameId && nonce ? /* @__PURE__ */ jsxRuntime.jsx("iframe", { ref: frame, title: opened.artifactId, "data-testid": "rhythm-artifact-frame", "data-frame-id": frameId, sandbox: "allow-scripts", srcDoc: documentSource(opened, nonce) }) : null
        ] }) : /* @__PURE__ */ jsxRuntime.jsx("p", { role: "status", children: "Artifacts are locked until the host explicitly grants this security gate." })
      ]
    }
  );
}
var iconSet = {
  activity: Icons__namespace.Activity,
  archive: Icons__namespace.Archive,
  attach: Icons__namespace.Paperclip,
  bell: Icons__namespace.Bell,
  book: Icons__namespace.BookOpen,
  calendar: Icons__namespace.Calendar,
  check: Icons__namespace.Check,
  chevronDown: Icons__namespace.ChevronDown,
  chevronRight: Icons__namespace.ChevronRight,
  close: Icons__namespace.X,
  copy: Icons__namespace.Copy,
  delete: Icons__namespace.Trash2,
  download: Icons__namespace.Download,
  filter: Icons__namespace.ListFilter,
  history: Icons__namespace.History,
  link: Icons__namespace.Link,
  mail: Icons__namespace.Mail,
  menu: Icons__namespace.Menu,
  more: Icons__namespace.Ellipsis,
  plus: Icons__namespace.Plus,
  refresh: Icons__namespace.RefreshCw,
  rename: Icons__namespace.Pencil,
  search: Icons__namespace.Search,
  settings: Icons__namespace.Settings2,
  sliders: Icons__namespace.SlidersHorizontal,
  sparkles: Icons__namespace.Sparkles,
  upload: Icons__namespace.Upload,
  users: Icons__namespace.Users,
  warning: Icons__namespace.TriangleAlert
};
function Icon({ name, size = 17, ...props }) {
  const Component = iconSet[name];
  return /* @__PURE__ */ jsxRuntime.jsx(Component, { "aria-hidden": "true", size, strokeWidth: 1.8, ...props });
}
function FocusDialog({
  open,
  title,
  description,
  onClose,
  children,
  testId,
  wide = false
}) {
  const panelRef = react.useRef(null);
  const returnFocusRef = react.useRef(null);
  const restoreFrameRef = react.useRef(null);
  const onCloseRef = react.useRef(onClose);
  const openRef = react.useRef(open);
  onCloseRef.current = onClose;
  openRef.current = open;
  const scheduleFocusRestore = () => {
    if (restoreFrameRef.current !== null) cancelAnimationFrame(restoreFrameRef.current);
    restoreFrameRef.current = requestAnimationFrame(() => {
      restoreFrameRef.current = null;
      if (openRef.current) return;
      const returnTarget = returnFocusRef.current;
      if (!returnTarget?.isConnected) {
        returnFocusRef.current = null;
        return;
      }
      returnTarget.focus({ preventScroll: true });
      if (document.activeElement === returnTarget) returnFocusRef.current = null;
    });
  };
  const requestClose = () => {
    onCloseRef.current();
    scheduleFocusRestore();
  };
  react.useLayoutEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    const activeElement = document.activeElement;
    if (!returnFocusRef.current && activeElement instanceof HTMLElement && !panel?.contains(activeElement)) {
      returnFocusRef.current = activeElement;
    }
    const focusable = panel?.querySelector("[data-autofocus]") ?? panel?.querySelector('button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex="-1"])');
    focusable?.focus();
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        requestClose();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const items = [...panel.querySelectorAll('button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex="-1"])')];
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      }
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      scheduleFocusRestore();
    };
  }, [open]);
  if (!open) return null;
  return /* @__PURE__ */ jsxRuntime.jsx("div", { className: "dialog-backdrop", role: "presentation", onMouseDown: (event) => {
    if (event.target === event.currentTarget) requestClose();
  }, children: /* @__PURE__ */ jsxRuntime.jsxs("div", { ref: panelRef, className: `dialog-panel ${wide ? "dialog-wide" : ""}`, role: "dialog", "aria-modal": "true", "aria-labelledby": `${testId}-title`, "aria-describedby": description ? `${testId}-description` : void 0, "data-testid": testId, children: [
    /* @__PURE__ */ jsxRuntime.jsxs("header", { className: "dialog-header", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntime.jsx("h2", { id: `${testId}-title`, children: title }),
        description && /* @__PURE__ */ jsxRuntime.jsx("p", { id: `${testId}-description`, children: description })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "icon-button", type: "button", onClick: requestClose, "aria-label": `Close ${title}`, "data-testid": `${testId}-close`, children: /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "close" }) })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsx("div", { className: "dialog-body", children })
  ] }) });
}
var sourceOrder = ["rhythm", "planning_center", "google_calendar", "gmail"];
var sourceLabels = { rhythm: "Rhythm", planning_center: "Planning Center", google_calendar: "Google Calendar", gmail: "Gmail" };
var triggerCatalog = {
  rhythm: [
    { key: "rhythm.task_due", label: "Task is approaching its due date" },
    { key: "rhythm.project_step_due", label: "Project step is approaching its due date" },
    { key: "rhythm.plan_assembled", label: "Plan is assembled" }
  ],
  planning_center: [
    { key: "pco.plan_upcoming", label: "Plan is upcoming" },
    { key: "pco.volunteer_declined", label: "Volunteer declined" },
    { key: "pco.volunteer_confirmed", label: "Volunteer confirmed" },
    { key: "pco.position_open", label: "Position is open" }
  ],
  google_calendar: [{ key: "google_calendar.event_matches", label: "Calendar event matches filter" }],
  gmail: [{ key: "gmail.message_matches", label: "Gmail message matches filter" }]
};
var actionCatalog = [
  { type: "create_task", label: "Create task" },
  { type: "create_project_from_template", label: "Create project from template" },
  { type: "tag_task", label: "Tag task" },
  { type: "send_notification", label: "Send notification" },
  { type: "auto_schedule", label: "Auto-schedule task" },
  { type: "create_reservation", label: "Create reservation" }
];
function allowedActions(source) {
  if (source === "planning_center") return actionCatalog.filter((action) => ["create_task", "create_project_from_template"].includes(action.type));
  if (source === "google_calendar") return actionCatalog;
  return actionCatalog.filter((action) => action.type !== "create_reservation");
}
var conditionFields = {
  rhythm: ["title", "notes"],
  planning_center: ["title", "serviceTypeName", "teamName", "positionName", "planDate"],
  google_calendar: ["title", "description", "location", "eventType"],
  gmail: ["subject", "fromEmail", "fromName", "snippet", "labelIds"]
};
function dateTimeLabel(value) {
  if (!value) return "Never";
  return value.slice(0, 16).replace("T", " ");
}
function suggestedName(source) {
  if (source === "gmail") return "Gmail message matches filter";
  if (source === "google_calendar") return "Calendar event matches filter";
  if (source === "planning_center") return "Planning Center plan upcoming";
  return "Rhythm task due";
}
function draftForRule(rule, catalog) {
  const source = rule?.source ?? "rhythm";
  const triggers = catalog.triggers[source] ?? triggerCatalog[source];
  const actions = catalog.actions.length ? catalog.actions : actionCatalog;
  return {
    name: rule?.name ?? "",
    source,
    triggerKey: rule?.triggerKey ?? triggers[0]?.key ?? "",
    actionType: rule?.actionType ?? (actions.find((action) => allowedActions(source).some((allowed) => allowed.type === action.type))?.type ?? "create_task"),
    conditions: structuredClone(rule?.conditions ?? []),
    actionConfig: { ...rule?.actionConfig ?? {} },
    sourceAccountId: rule?.sourceAccountId ?? catalog.providers.find((provider) => provider.source === source)?.accountId ?? null
  };
}
var fallbackCatalog = { providers: [], triggers: triggerCatalog, actions: actionCatalog };
function StatePanel({ state, onRetry, onCreate }) {
  if (state === "loading") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "automations-state", role: "status", "aria-live": "polite", "data-testid": "page-state-loading", children: [
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Loading automations" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Gathering rules and the current automation catalog." })
  ] });
  if (state === "empty") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "automations-state", role: "status", "data-testid": "page-state-empty", children: [
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "No automations yet" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Turn a repeated handoff into a dependable Rhythm rule." }),
    /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "primary-button", type: "button", onClick: onCreate, "data-testid": "automations-empty-create", children: [
      /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "plus", size: 15 }),
      "Create automation"
    ] })
  ] });
  if (state === "server_error") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "automations-state danger", role: "alert", "data-testid": "page-state-server-error", children: [
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Automations could not be loaded" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "The automation service returned a temporary error." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
  ] });
  if (state === "forbidden") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "automations-state warning", role: "alert", "data-testid": "page-state-forbidden", children: [
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Workspace access required" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Ask a workspace owner to grant access to owned automation rules." })
  ] });
  return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "automations-state warning", role: "status", "data-testid": "page-state-unavailable", children: [
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Automations are unavailable" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Reconnect the automation service before rules can be loaded or changed." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
  ] });
}
function BuilderDialog({ open, editing, catalog, canMutate, onClose, onSubmit }) {
  const [draft, setDraft] = react.useState(() => draftForRule(editing, catalog));
  const [error, setError] = react.useState("");
  react.useEffect(() => {
    if (!open) return;
    setDraft(draftForRule(editing, catalog));
    setError("");
  }, [editing, open, catalog]);
  const updateSource = (source) => {
    const triggers2 = catalog.triggers[source] ?? triggerCatalog[source];
    const provider2 = catalog.providers.find((item) => item.source === source);
    setDraft((current) => ({ ...current, source, triggerKey: triggers2[0]?.key ?? "", actionType: allowedActions(source)[0]?.type ?? "create_task", conditions: [], actionConfig: {}, sourceAccountId: provider2?.accountId ?? null }));
    setError("");
  };
  const addCondition = () => setDraft((current) => ({ ...current, conditions: [...current.conditions, { field: conditionFields[current.source][0] ?? "", operator: "equals", value: "" }] }));
  const setCondition = (index, patch) => setDraft((current) => ({ ...current, conditions: current.conditions.map((condition, itemIndex) => itemIndex === index ? { ...condition, ...patch } : condition) }));
  const removeCondition = (index) => setDraft((current) => ({ ...current, conditions: current.conditions.filter((_, itemIndex) => itemIndex !== index) }));
  const submit = (event) => {
    event.preventDefault();
    onSubmit({ ...draft, conditions: draft.conditions.filter((condition) => condition.value.trim()) });
  };
  const actions = (catalog.actions.length ? catalog.actions : actionCatalog).filter((action2) => allowedActions(draft.source).some((allowed) => allowed.type === action2.type));
  const triggers = catalog.triggers[draft.source] ?? triggerCatalog[draft.source];
  const action = actions.find((item) => item.type === draft.actionType);
  const provider = catalog.providers.find((item) => item.source === draft.source);
  const providerReady = !provider || provider.status === "connected";
  const reviewName = draft.name.trim() || suggestedName(draft.source);
  return /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open, onClose, title: editing ? "Edit automation" : "New automation", description: "Choose a source signal, narrow it if needed, then decide what Rhythm should do.", testId: "automations-builder-dialog", wide: true, children: /* @__PURE__ */ jsxRuntime.jsx("form", { className: "automation-builder", onSubmit: submit, children: /* @__PURE__ */ jsxRuntime.jsxs("fieldset", { disabled: !canMutate, "aria-describedby": !canMutate ? "automations-read-only" : void 0, children: [
    error && /* @__PURE__ */ jsxRuntime.jsx("div", { className: "automation-form-error", role: "alert", "data-testid": "automation-builder-error", children: error }),
    /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "builder-section", "aria-labelledby": "automation-source-heading", children: [
      /* @__PURE__ */ jsxRuntime.jsx("h3", { id: "automation-source-heading", children: "Source" }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "builder-grid", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "automation-field span-2", children: [
          "Automation name",
          /* @__PURE__ */ jsxRuntime.jsx("input", { "data-autofocus": true, value: draft.name, onChange: (event) => setDraft((current) => ({ ...current, name: event.target.value })), placeholder: suggestedName(draft.source), "data-testid": "automation-name" })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "automation-field", children: [
          "Provider",
          /* @__PURE__ */ jsxRuntime.jsx("select", { value: draft.source, onChange: (event) => updateSource(event.target.value), "data-testid": "automation-source", children: sourceOrder.map((source) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: source, children: sourceLabels[source] }, source)) })
        ] }),
        draft.source !== "rhythm" && /* @__PURE__ */ jsxRuntime.jsxs("p", { className: "automation-provider-state", role: "status", "data-testid": "automation-provider-state", children: [
          provider?.accountLabel ?? "No provider account",
          " \xB7 ",
          provider?.status ?? "catalog unavailable"
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "builder-section", "aria-labelledby": "automation-trigger-heading", children: [
      /* @__PURE__ */ jsxRuntime.jsx("h3", { id: "automation-trigger-heading", children: "Trigger" }),
      /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "automation-field", children: [
        "Trigger",
        /* @__PURE__ */ jsxRuntime.jsx("select", { value: draft.triggerKey, onChange: (event) => setDraft((current) => ({ ...current, triggerKey: event.target.value })), "data-testid": "automation-trigger", children: triggers.map((trigger) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: trigger.key, children: trigger.label }, trigger.key)) })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "builder-section", "aria-labelledby": "automation-conditions-heading", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
        /* @__PURE__ */ jsxRuntime.jsx("h3", { id: "automation-conditions-heading", children: "Conditions" }),
        /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "secondary-button", type: "button", onClick: addCondition, "data-testid": "automation-add-condition", children: [
          /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "plus", size: 14 }),
          "Add condition"
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsx("div", { className: "conditions-list", children: draft.conditions.map((condition, index) => /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "condition-row", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "automation-field", children: [
          "Field",
          /* @__PURE__ */ jsxRuntime.jsx("select", { value: condition.field, onChange: (event) => setCondition(index, { field: event.target.value }), "data-testid": `automation-condition-field-${index}`, children: conditionFields[draft.source].map((field) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: field, children: field }, field)) })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "automation-field", children: [
          "Operator",
          /* @__PURE__ */ jsxRuntime.jsxs("select", { value: condition.operator, onChange: (event) => setCondition(index, { operator: event.target.value }), "data-testid": `automation-condition-operator-${index}`, children: [
            /* @__PURE__ */ jsxRuntime.jsx("option", { value: "equals", children: "equals" }),
            /* @__PURE__ */ jsxRuntime.jsx("option", { value: "not_equals", children: "not equals" }),
            /* @__PURE__ */ jsxRuntime.jsx("option", { value: "contains", children: "contains" }),
            /* @__PURE__ */ jsxRuntime.jsx("option", { value: "not_contains", children: "not contains" })
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "automation-field", children: [
          "Value",
          /* @__PURE__ */ jsxRuntime.jsx("input", { value: condition.value, onChange: (event) => setCondition(index, { value: event.target.value }), "data-testid": `automation-condition-value-${index}` })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "icon-button", type: "button", "aria-label": `Remove condition ${index + 1}`, onClick: () => removeCondition(index), "data-testid": `automation-condition-remove-${index}`, children: /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "delete", size: 15 }) })
      ] }, index)) })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "builder-section", "aria-labelledby": "automation-action-heading", children: [
      /* @__PURE__ */ jsxRuntime.jsx("h3", { id: "automation-action-heading", children: "Action" }),
      /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "automation-field span-2", children: [
        "Action",
        /* @__PURE__ */ jsxRuntime.jsx("select", { value: draft.actionType, onChange: (event) => setDraft((current) => ({ ...current, actionType: event.target.value })), "data-testid": "automation-action", children: actions.map((action2) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: action2.type, children: action2.label }, action2.type)) })
      ] }),
      action?.configFields?.map((field) => /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "automation-field span-2", children: [
        field.label,
        /* @__PURE__ */ jsxRuntime.jsx("input", { value: draft.actionConfig[field.key] ?? "", onChange: (event) => setDraft((current) => ({ ...current, actionConfig: { ...current.actionConfig, [field.key]: event.target.value } })), "data-testid": `automation-action-config-${field.key}` })
      ] }, field.key))
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "builder-review", "aria-labelledby": "automation-review-heading", "data-testid": "automation-review", children: [
      /* @__PURE__ */ jsxRuntime.jsx("h3", { id: "automation-review-heading", children: reviewName }),
      /* @__PURE__ */ jsxRuntime.jsxs("dl", { children: [
        /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
          /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Provider" }),
          /* @__PURE__ */ jsxRuntime.jsx("dd", { children: provider?.accountLabel ?? sourceLabels[draft.source] })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
          /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Trigger" }),
          /* @__PURE__ */ jsxRuntime.jsx("dd", { children: triggers.find((trigger) => trigger.key === draft.triggerKey)?.label })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
          /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Action" }),
          /* @__PURE__ */ jsxRuntime.jsx("dd", { children: actions.find((action2) => action2.type === draft.actionType)?.label })
        ] })
      ] })
    ] }),
    !providerReady && /* @__PURE__ */ jsxRuntime.jsxs("p", { role: "alert", "data-testid": "automation-provider-write-blocked", children: [
      "Reconnect ",
      provider?.accountLabel ?? sourceLabels[draft.source],
      " before creating or updating this automation."
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("footer", { className: "builder-actions", children: [
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: onClose, "data-testid": "automation-builder-cancel", children: "Cancel" }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "submit", disabled: !providerReady, "data-testid": "automation-builder-submit", children: editing ? "Save automation" : "Create automation" })
    ] })
  ] }) }) });
}
function AutomationRuleRow({ rule, onSelect, onToggle, onPreview, onEdit, onDelete, canMutate, canWrite }) {
  const labelId = react.useId();
  return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "automation-rule", "data-testid": `automation-rule-${rule.id}`, children: [
    /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "rule-select", type: "button", onClick: onSelect, "data-testid": `automation-select-${rule.id}`, children: [
      /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "rule-title-line", children: [
        /* @__PURE__ */ jsxRuntime.jsx("strong", { children: rule.name }),
        /* @__PURE__ */ jsxRuntime.jsx("span", { className: `rule-status ${rule.enabled ? "active" : ""}`, children: rule.enabled ? "Enabled" : "Paused" })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("small", { children: [
        rule.triggerLabel,
        " \u2192 ",
        rule.actionLabel
      ] }),
      /* @__PURE__ */ jsxRuntime.jsx("em", { children: rule.accountLabel })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "rule-actions", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "automation-toggle", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "sr-only", id: labelId, children: [
          rule.enabled ? "Disable" : "Enable",
          " ",
          rule.name
        ] }),
        /* @__PURE__ */ jsxRuntime.jsx("input", { type: "checkbox", disabled: !canWrite, checked: rule.enabled, "aria-labelledby": labelId, onChange: (event) => onToggle(event.target.checked), "data-testid": `automation-toggle-${rule.id}` })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: !canWrite, onClick: onEdit, "data-testid": `automation-edit-${rule.id}`, children: "Edit" }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "icon-button danger-control", type: "button", disabled: !canMutate, "aria-label": `Delete ${rule.name}`, onClick: onDelete, "data-testid": `automation-delete-${rule.id}`, children: /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "delete", size: 15 }) })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "rule-inspect", type: "button", onClick: onPreview, "data-testid": `automation-preview-${rule.id}`, children: [
      /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "search", size: 14 }),
      "Preview history"
    ] })
  ] });
}
function AutomationsScreen() {
  const { automations: gateway } = useRhythmDomainGateway();
  const host = useRhythmHost();
  const [surfaceState, setSurfaceState] = react.useState("loading");
  const [rules, setRules] = react.useState([]);
  const [selectedRuleId, setSelectedRuleId] = react.useState(null);
  const [builderOpen, setBuilderOpen] = react.useState(false);
  const [editingRule, setEditingRule] = react.useState(null);
  const [previewRuleId, setPreviewRuleId] = react.useState(null);
  const [deleteTarget, setDeleteTarget] = react.useState(null);
  const [catalogStatus, setCatalogStatus] = react.useState("");
  const [catalog, setCatalog] = react.useState(fallbackCatalog);
  const [fetchedPreview, setFetchedPreview] = react.useState(null);
  const [resyncStatus, setResyncStatus] = react.useState("");
  const [mutationPending, setMutationPending] = react.useState(false);
  const [resyncPending, setResyncPending] = react.useState(false);
  const mountedRef = react.useRef(true);
  const listGeneration = react.useRef(0);
  const previewGeneration = react.useRef(0);
  const canMutate = host.currentUser.capabilities?.includes("automations.write") ?? false;
  const handleError = (error) => {
    const kind = error instanceof RhythmGatewayError ? error.kind : "server_error";
    setSurfaceState(kind === "forbidden" ? "forbidden" : kind === "not_found" ? "unavailable" : kind === "unavailable" ? "unavailable" : "server_error");
  };
  const load = async () => {
    const generation = ++listGeneration.current;
    setSurfaceState("loading");
    try {
      const loaded = await gateway.list();
      if (!mountedRef.current || generation !== listGeneration.current) return;
      setRules(loaded);
      setSurfaceState(loaded.length ? "ready" : "empty");
    } catch (error) {
      if (!mountedRef.current || generation !== listGeneration.current) return;
      handleError(error);
    }
  };
  react.useEffect(() => {
    mountedRef.current = true;
    void load();
    return () => {
      mountedRef.current = false;
      listGeneration.current += 1;
      previewGeneration.current += 1;
    };
  }, [gateway]);
  react.useEffect(() => {
    if (!gateway.catalog) return;
    let active = true;
    void gateway.catalog().then((loaded) => {
      if (active) {
        setCatalog(loaded);
        setCatalogStatus(loaded.providers.some((provider) => provider.status === "stale") ? "A provider catalog is stale; reconnect or resync before changing dependent rules." : "");
      }
    }).catch(() => {
      if (active) setCatalogStatus("Catalog unavailable. Existing rules remain available to inspect.");
    });
    return () => {
      active = false;
    };
  }, [gateway]);
  const showsRules = surfaceState === "ready";
  const groupedRules = sourceOrder.map((source) => ({ source, rules: rules.filter((rule) => rule.source === source) })).filter((group) => group.rules.length);
  const enabledCount = rules.filter((rule) => rule.enabled).length;
  const inspectorRule = rules.find((rule) => rule.id === selectedRuleId) ?? null;
  const previewRule = rules.find((rule) => rule.id === previewRuleId) ?? null;
  const providerReady = (source) => {
    const provider = catalog.providers.find((item) => item.source === source);
    return !provider || provider.status === "connected";
  };
  const openBuilder = (rule = null) => {
    setEditingRule(rule);
    setBuilderOpen(true);
  };
  const closeBuilder = () => {
    setBuilderOpen(false);
    setEditingRule(null);
  };
  const submitBuilder = async (draft) => {
    if (!canMutate || !providerReady(draft.source)) return;
    const name = draft.name.trim() || suggestedName(draft.source);
    const triggerLabel = (catalog.triggers[draft.source] ?? triggerCatalog[draft.source]).find((trigger) => trigger.key === draft.triggerKey)?.label ?? "";
    const actionLabel = (catalog.actions.length ? catalog.actions : actionCatalog).find((action) => action.type === draft.actionType)?.label ?? "";
    setMutationPending(true);
    try {
      if (editingRule) {
        const updated = await gateway.update(editingRule.id, { name, source: draft.source, sourceAccountId: draft.sourceAccountId, triggerKey: draft.triggerKey, triggerLabel, actionType: draft.actionType, actionLabel, actionConfig: draft.actionConfig, enabled: editingRule.enabled, conditions: draft.conditions });
        setRules((current) => current.map((rule) => rule.id === updated.id ? updated : rule));
      } else {
        const created = await gateway.create({ name, source: draft.source, sourceAccountId: draft.sourceAccountId, triggerKey: draft.triggerKey, triggerLabel, actionType: draft.actionType, actionLabel, actionConfig: draft.actionConfig, conditions: draft.conditions, enabled: true });
        setRules((current) => [...current, created]);
        setSelectedRuleId(created.id);
      }
      closeBuilder();
    } catch (error) {
      handleError(error);
    } finally {
      setMutationPending(false);
    }
  };
  const toggleRule = async (rule, enabled) => {
    if (!canMutate || !providerReady(rule.source)) return;
    setMutationPending(true);
    try {
      const updated = await gateway.update(rule.id, { enabled });
      setRules((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (error) {
      handleError(error);
    } finally {
      setMutationPending(false);
    }
  };
  const confirmDelete = async () => {
    if (!deleteTarget) return;
    if (!canMutate) return;
    setMutationPending(true);
    try {
      await gateway.delete(deleteTarget.id);
      setRules((current) => current.filter((rule) => rule.id !== deleteTarget.id));
      if (selectedRuleId === deleteTarget.id) setSelectedRuleId(null);
      setDeleteTarget(null);
    } catch (error) {
      handleError(error);
    } finally {
      setMutationPending(false);
    }
  };
  const openPreview = (rule) => {
    const generation = ++previewGeneration.current;
    setPreviewRuleId(rule.id);
    setFetchedPreview(null);
    if (!gateway.preview) return;
    void gateway.preview(rule.id).then((preview) => {
      if (mountedRef.current && generation === previewGeneration.current) setFetchedPreview({ id: rule.id, summary: preview.summary, matchedAt: preview.matchedAt, matchCount: preview.matchCount });
    }).catch(() => {
      if (mountedRef.current && generation === previewGeneration.current) setFetchedPreview({ id: rule.id, summary: "Preview could not be refreshed. Historical details remain available.", matchedAt: rule.lastMatchedAt, matchCount: rule.matchCountLastRun });
    });
  };
  const resyncRule = async (rule) => {
    if (!canMutate || !gateway.resync || resyncPending) return;
    setResyncPending(true);
    setResyncStatus(`Resyncing ${rule.name}\u2026`);
    try {
      const updated = await gateway.resync(rule.id);
      if (!mountedRef.current) return;
      setRules((current) => current.map((item) => item.id === updated.id ? updated : item));
      setResyncStatus(`${rule.name} resynced. ${updated.matchCountLastRun} matched last run.`);
    } catch {
      if (mountedRef.current) setResyncStatus(`${rule.name} could not resync. Reconnect its provider and retry.`);
    } finally {
      if (mountedRef.current) setResyncPending(false);
    }
  };
  return /* @__PURE__ */ jsxRuntime.jsxs(ScreenRoot, { screenName: "Automations", testId: "rhythm-automations-screen", children: [
    /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "page-shell pg-automations", "aria-busy": surfaceState === "loading", children: [
      /* @__PURE__ */ jsxRuntime.jsx("header", { className: "automations-header", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "automations-heading", children: [
        /* @__PURE__ */ jsxRuntime.jsx("h1", { children: "Automations" }),
        /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Create and inspect rules that turn incoming signals into tasks, schedules, or notifications." })
      ] }) }),
      catalogStatus && /* @__PURE__ */ jsxRuntime.jsx("p", { role: "status", "data-testid": "automation-catalog-status", children: catalogStatus }),
      !canMutate && /* @__PURE__ */ jsxRuntime.jsx("p", { role: "status", "data-testid": "automations-read-only", children: "You can inspect automations, but this account cannot create, edit, pause, or delete rules." }),
      !showsRules && /* @__PURE__ */ jsxRuntime.jsx(StatePanel, { state: surfaceState, onRetry: () => void load(), onCreate: () => openBuilder() }),
      showsRules && /* @__PURE__ */ jsxRuntime.jsxs(jsxRuntime.Fragment, { children: [
        /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "automations-overview", "aria-label": "Automation summary", children: [
          /* @__PURE__ */ jsxRuntime.jsxs("dl", { children: [
            /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Rules" }),
              /* @__PURE__ */ jsxRuntime.jsx("dd", { "data-testid": "automations-rule-count", children: rules.length })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Enabled" }),
              /* @__PURE__ */ jsxRuntime.jsx("dd", { "data-testid": "automations-enabled-count", children: enabledCount })
            ] })
          ] }),
          /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "primary-button", type: "button", onClick: () => openBuilder(), disabled: mutationPending || !canMutate, "data-testid": "automations-new", children: [
            /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "plus", size: 15 }),
            "New automation"
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "automation-workspace", "aria-label": "Automation rules and inspector", children: [
          /* @__PURE__ */ jsxRuntime.jsx("div", { className: "automation-groups", tabIndex: 0, "aria-label": "Automation rule groups", children: groupedRules.map((group) => /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "automation-group", "data-testid": `automation-group-${group.source}`, "aria-labelledby": `automation-group-${group.source}-title`, children: [
            /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("h2", { id: `automation-group-${group.source}-title`, children: sourceLabels[group.source] }),
              /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
                group.rules.length,
                " ",
                group.rules.length === 1 ? "rule" : "rules"
              ] })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsx("div", { className: "automation-rule-list", children: group.rules.map((rule) => /* @__PURE__ */ jsxRuntime.jsx(
              AutomationRuleRow,
              {
                rule,
                onSelect: () => setSelectedRuleId(rule.id),
                onToggle: (enabled) => void toggleRule(rule, enabled),
                onPreview: () => openPreview(rule),
                onEdit: () => openBuilder(rule),
                onDelete: () => setDeleteTarget(rule),
                canMutate,
                canWrite: canMutate && providerReady(rule.source)
              },
              rule.id
            )) })
          ] }, group.source)) }),
          /* @__PURE__ */ jsxRuntime.jsx("aside", { className: "automation-inspector", "aria-label": "Automation inspector", "data-testid": "automation-inspector", children: inspectorRule ? /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "automation-inspector-content", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("span", { children: sourceLabels[inspectorRule.source] }),
              /* @__PURE__ */ jsxRuntime.jsx("h2", { children: inspectorRule.name }),
              /* @__PURE__ */ jsxRuntime.jsx("p", { children: inspectorRule.previewSummary })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("dl", { children: [
              /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Status" }),
                /* @__PURE__ */ jsxRuntime.jsx("dd", { children: inspectorRule.enabled ? "Enabled" : "Paused" })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Account" }),
                /* @__PURE__ */ jsxRuntime.jsx("dd", { children: inspectorRule.accountLabel })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Trigger" }),
                /* @__PURE__ */ jsxRuntime.jsx("dd", { children: inspectorRule.triggerLabel })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Action" }),
                /* @__PURE__ */ jsxRuntime.jsx("dd", { children: inspectorRule.actionLabel })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Conditions" }),
                /* @__PURE__ */ jsxRuntime.jsx("dd", { children: inspectorRule.conditions.length || "None" })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Matches last run" }),
                /* @__PURE__ */ jsxRuntime.jsx("dd", { children: inspectorRule.matchCountLastRun })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Last matched" }),
                /* @__PURE__ */ jsxRuntime.jsx("dd", { children: dateTimeLabel(inspectorRule.lastMatchedAt) })
              ] })
            ] }),
            catalog.providers.find((provider) => provider.source === inspectorRule.source)?.status === "stale" && /* @__PURE__ */ jsxRuntime.jsx("p", { role: "alert", "data-testid": "automation-provider-stale", children: "This provider is stale. Reconnect it before depending on new matches." }),
            gateway.resync && /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: !canMutate || mutationPending || resyncPending, onClick: () => void resyncRule(inspectorRule), "data-testid": "automation-resync", children: "Resync rule" }),
            resyncStatus && /* @__PURE__ */ jsxRuntime.jsx("p", { role: "status", "aria-live": "polite", "data-testid": "automation-resync-status", children: resyncStatus })
          ] }) : /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "automation-inspector-empty", children: [
            /* @__PURE__ */ jsxRuntime.jsx("strong", { children: "Select an automation" }),
            /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Choose a rule to inspect its trigger, action, account, and latest match evidence." })
          ] }) })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsx(BuilderDialog, { open: builderOpen, editing: editingRule, catalog, canMutate, onClose: closeBuilder, onSubmit: (draft) => void submitBuilder(draft) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(previewRule), onClose: () => {
      previewGeneration.current += 1;
      setPreviewRuleId(null);
    }, title: previewRule?.name ?? "Automation preview", description: "Historical rule metadata. Preview does not execute this automation.", testId: "automation-preview-dialog", wide: true, children: previewRule && /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "automation-preview", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "preview-path", children: [
        /* @__PURE__ */ jsxRuntime.jsx("span", { children: sourceLabels[previewRule.source] }),
        /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "chevronRight", size: 15 }),
        /* @__PURE__ */ jsxRuntime.jsx("strong", { children: previewRule.actionLabel })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { className: "preview-summary", "data-testid": "automation-preview-summary", children: fetchedPreview?.id === previewRule.id ? fetchedPreview.summary : previewRule.previewSummary }),
      /* @__PURE__ */ jsxRuntime.jsxs("dl", { children: [
        /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
          /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Matches last run" }),
          /* @__PURE__ */ jsxRuntime.jsxs("dd", { children: [
            fetchedPreview?.id === previewRule.id ? fetchedPreview.matchCount : previewRule.matchCountLastRun,
            " ",
            (fetchedPreview?.id === previewRule.id ? fetchedPreview.matchCount : previewRule.matchCountLastRun) === 1 ? "match" : "matches",
            " last run"
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
          /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Last matched" }),
          /* @__PURE__ */ jsxRuntime.jsx("dd", { children: dateTimeLabel(fetchedPreview?.id === previewRule.id ? fetchedPreview.matchedAt : previewRule.lastMatchedAt) })
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsx("div", { className: "preview-actions", children: /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", "data-autofocus": true, onClick: () => {
        previewGeneration.current += 1;
        setPreviewRuleId(null);
      }, "data-testid": "automation-preview-close", children: "Close preview" }) })
    ] }) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(deleteTarget), onClose: () => setDeleteTarget(null), title: deleteTarget ? `Delete ${deleteTarget.name}?` : "Delete automation?", description: "This removes the rule from this workspace. This cannot be undone.", testId: "automation-delete-dialog", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => setDeleteTarget(null), "data-testid": "automation-delete-cancel", children: "Cancel" }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "danger-button", type: "button", disabled: mutationPending, onClick: () => void confirmDelete(), "data-testid": "automation-delete-confirm", children: "Delete automation" })
    ] }) })
  ] });
}
function HeaderTaskAction({
  onClick,
  disabled = false,
  describedBy,
  testId,
  label = "Add task"
}) {
  return /* @__PURE__ */ jsxRuntime.jsxs(
    "button",
    {
      className: "primary-button page-task-action",
      type: "button",
      disabled,
      "aria-describedby": describedBy,
      onClick,
      "data-testid": testId,
      children: [
        /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "plus", size: 15 }),
        /* @__PURE__ */ jsxRuntime.jsx("span", { children: label })
      ]
    }
  );
}
function TaskCreateForm({
  idPrefix,
  onSubmit,
  onCancel,
  members,
  testIds,
  titleRef,
  titleError,
  onTitleChange,
  defaultScheduledDate = "",
  disabled = false,
  describedBy,
  noValidate = false
}) {
  const titleErrorId = titleError ? `${idPrefix}-title-error` : void 0;
  const titleDescription = [titleErrorId, describedBy].filter(Boolean).join(" ") || void 0;
  return /* @__PURE__ */ jsxRuntime.jsx("form", { className: "task-editor-form", onSubmit, noValidate, children: /* @__PURE__ */ jsxRuntime.jsxs("fieldset", { disabled, "aria-disabled": disabled || void 0, "aria-describedby": describedBy, "data-testid": testIds.mutations, children: [
    /* @__PURE__ */ jsxRuntime.jsx("legend", { className: "sr-only", children: "New task details" }),
    /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "task-editor-field", children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Task title" }),
      /* @__PURE__ */ jsxRuntime.jsx(
        "input",
        {
          ref: titleRef,
          name: "title",
          required: true,
          placeholder: "What needs doing?",
          autoComplete: "off",
          "aria-invalid": titleError ? "true" : void 0,
          "aria-describedby": titleDescription,
          onChange: onTitleChange,
          "data-autofocus": true,
          "data-testid": testIds.title
        }
      )
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "task-editor-field", children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Task notes" }),
      /* @__PURE__ */ jsxRuntime.jsx(
        "textarea",
        {
          name: "notes",
          rows: 4,
          placeholder: "Add context or a next step",
          "data-testid": testIds.notes
        }
      )
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "task-editor-pair", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "task-editor-field", children: [
        /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Scheduled date" }),
        /* @__PURE__ */ jsxRuntime.jsx("input", { name: "scheduledDate", type: "date", defaultValue: defaultScheduledDate, "data-testid": testIds.scheduledDate })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "task-editor-field", children: [
        /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Due date" }),
        /* @__PURE__ */ jsxRuntime.jsx("input", { name: "dueDate", type: "date", "data-testid": testIds.dueDate })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "task-editor-section", "aria-labelledby": `${idPrefix}-people-title`, children: [
      /* @__PURE__ */ jsxRuntime.jsx("div", { className: "task-editor-section-head", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntime.jsx("h3", { id: `${idPrefix}-people-title`, children: "People" }),
        /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Assign one collaborator now or add more after creating the task." })
      ] }) }),
      /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "task-editor-field", children: [
        /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Collaborator" }),
        /* @__PURE__ */ jsxRuntime.jsxs("select", { name: "collaboratorId", defaultValue: "", "data-testid": testIds.collaborator, children: [
          /* @__PURE__ */ jsxRuntime.jsx("option", { value: "", children: "No collaborator" }),
          members.map((person) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: person.id, children: person.name }, person.id))
        ] })
      ] })
    ] }),
    titleError && /* @__PURE__ */ jsxRuntime.jsx("p", { className: "task-editor-error", id: titleErrorId, role: "alert", "data-testid": testIds.error, children: titleError }),
    /* @__PURE__ */ jsxRuntime.jsxs("footer", { className: "task-editor-footer", children: [
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: onCancel, "data-testid": testIds.cancel, children: "Cancel" }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "submit", "data-testid": testIds.submit, children: "Create task" })
    ] })
  ] }) });
}
function Metric({ label, value }) {
  return /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
    /* @__PURE__ */ jsxRuntime.jsx("dt", { children: label }),
    /* @__PURE__ */ jsxRuntime.jsx("dd", { children: value })
  ] });
}
function StatePanel2({ state, onRetry, onEmpty, canWrite }) {
  if (state === "loading") {
    return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "dashboard-state loading", role: "status", "aria-live": "polite", "data-testid": "page-state-loading", children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Refreshing planning data" }),
      /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Loading dashboard\u2026" }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Fetching the summary and active project steps." }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "state-skeleton", "aria-hidden": "true", children: [
        /* @__PURE__ */ jsxRuntime.jsx("span", {}),
        /* @__PURE__ */ jsxRuntime.jsx("span", {}),
        /* @__PURE__ */ jsxRuntime.jsx("span", {})
      ] })
    ] });
  }
  if (state === "empty") {
    return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "dashboard-state", role: "status", "data-testid": "page-state-empty", children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "A clear workspace" }),
      /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "No planning work yet" }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Create the first task to give this week a starting point." }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", disabled: !canWrite, onClick: onEmpty, "data-testid": "dashboard-empty-primary", children: "Create the first task" })
    ] });
  }
  if (state === "server_error") {
    return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "dashboard-state danger", role: "alert", "data-testid": "page-state-server-error", children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Retryable server error" }),
      /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Dashboard could not load" }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { children: "The planning service returned a temporary error. Existing data remains unchanged." }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
    ] });
  }
  if (state === "forbidden") {
    return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "dashboard-state warning", role: "alert", "data-testid": "page-state-forbidden", children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Workspace permission required" }),
      /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Dashboard access is restricted" }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Ask a workspace administrator for planning access before viewing this summary." })
    ] });
  }
  return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "dashboard-state warning", role: "status", "data-testid": "page-state-unavailable", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Planning service prerequisite" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Planning data is unavailable" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Reconnect the planning service before refreshing tasks and projects." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
  ] });
}
function TaskEntry({ task, onInspect, onToggle, readonly }) {
  return /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "task-entry", children: [
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "task-toggle", type: "button", disabled: readonly, "aria-label": `${task.status === "done" ? "Reopen" : "Complete"} ${task.title}`, onClick: () => onToggle(task), "data-testid": `task-toggle-${task.id}`, children: /* @__PURE__ */ jsxRuntime.jsx("span", { "aria-hidden": "true", children: task.status === "done" ? "\u2713" : "\u25CB" }) }),
    /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "task-row", type: "button", onClick: () => onInspect(task), "data-status": task.status, "data-testid": `task-row-${task.id}`, children: [
      /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "row-copy", children: [
        /* @__PURE__ */ jsxRuntime.jsx("strong", { children: task.title }),
        /* @__PURE__ */ jsxRuntime.jsxs("small", { children: [
          task.collaboratorName ? `${task.collaboratorName} \xB7 ` : "",
          task.dueLabel
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "row-status", children: task.status })
    ] })
  ] });
}
function ProjectStepEntry({ step, onInspect, onToggle, readonly }) {
  return /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "task-entry", children: [
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "task-toggle", type: "button", disabled: readonly, "aria-label": `${step.status === "done" ? "Reopen" : "Complete"} ${step.title}`, onClick: () => onToggle(step), "data-testid": `project-step-toggle-${step.id}`, children: /* @__PURE__ */ jsxRuntime.jsx("span", { "aria-hidden": "true", children: step.status === "done" ? "\u2713" : "\u25CB" }) }),
    /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "task-row", type: "button", onClick: () => onInspect(step), "data-status": step.status, "data-testid": `project-step-row-${step.id}`, children: [
      /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "row-copy", children: [
        /* @__PURE__ */ jsxRuntime.jsx("strong", { children: step.title }),
        /* @__PURE__ */ jsxRuntime.jsx("small", { children: step.dueLabel })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "row-status", children: "step" })
    ] })
  ] });
}
function DashboardScreen() {
  const { dashboard: gateway } = useRhythmDomainGateway();
  const host = useRhythmHost();
  const canWrite = host.currentUser.capabilities?.includes("dashboard.write") ?? false;
  const [surfaceState, setSurfaceState] = react.useState("loading");
  const [summary, setSummary] = react.useState(null);
  const [members, setMembers] = react.useState([]);
  const [selectedTask, setSelectedTask] = react.useState(null);
  const [selectedStep, setSelectedStep] = react.useState(null);
  const [createOpen, setCreateOpen] = react.useState(false);
  const [titleError, setTitleError] = react.useState(false);
  const [mutationPending, setMutationPending] = react.useState(false);
  const taskTitleRef = react.useRef(null);
  const handleError = (error) => {
    const kind = error instanceof RhythmGatewayError ? error.kind : "server_error";
    setSurfaceState(kind === "forbidden" ? "forbidden" : kind === "unavailable" || kind === "not_found" ? "unavailable" : "server_error");
  };
  const load = async () => {
    setSurfaceState("loading");
    try {
      const [loadedSummary, loadedMembers] = await Promise.all([gateway.summary(), gateway.members()]);
      setSummary(loadedSummary);
      setMembers(loadedMembers);
      setSurfaceState(loadedSummary.tasks.length || loadedSummary.project ? "ready" : "empty");
    } catch (error) {
      handleError(error);
    }
  };
  react.useEffect(() => {
    void load();
  }, [gateway]);
  const isContentVisible = surfaceState === "ready";
  const tasks = summary?.tasks ?? [];
  const project = summary?.project ?? null;
  const todayTasks = tasks.filter((task) => task.bucket === "today");
  const pastDueTasks = tasks.filter((task) => task.bucket === "past-due" && task.status === "open");
  const weekTasks = tasks.filter((task) => task.bucket === "week" && task.status === "open");
  const unscheduledTasks = tasks.filter((task) => task.bucket === "unscheduled" && task.status === "open");
  const handoffTasks = tasks.filter((task) => task.collaboratorName && task.status === "open");
  const openCount = tasks.filter((task) => task.status === "open").length;
  const todayDone = todayTasks.filter((task) => task.status === "done").length;
  const projectSteps = project?.steps ?? [];
  const projectDone = projectSteps.filter((step) => step.status === "done").length;
  const projectNextStep = react.useMemo(() => projectSteps.find((step) => step.status === "open"), [projectSteps]);
  const toggleTask = async (task) => {
    if (!canWrite || mutationPending) return;
    setMutationPending(true);
    try {
      const updated = await gateway.updateTask(task.id, { status: task.status === "done" ? "open" : "done" });
      setSummary((current) => current && { ...current, tasks: current.tasks.map((item) => item.id === updated.id ? updated : item) });
    } catch (error) {
      handleError(error);
    } finally {
      setMutationPending(false);
    }
  };
  const toggleStep = async (step) => {
    if (!canWrite || mutationPending || !project) return;
    setMutationPending(true);
    try {
      const updated = await gateway.updateProjectStep(step.id, { status: step.status === "done" ? "open" : "done" });
      setSummary((current) => current && current.project && { ...current, project: { ...current.project, steps: current.project.steps.map((item) => item.id === updated.id ? updated : item) } });
    } catch (error) {
      handleError(error);
    } finally {
      setMutationPending(false);
    }
  };
  const createTask = async (event) => {
    event.preventDefault();
    if (!canWrite) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const title = String(data.get("title") ?? "").trim();
    if (!title) {
      setTitleError(true);
      taskTitleRef.current?.focus();
      return;
    }
    setMutationPending(true);
    try {
      const created = await gateway.createTask({
        title,
        notes: String(data.get("notes") ?? "").trim() || void 0,
        scheduledDate: String(data.get("scheduledDate") ?? "").trim() || void 0,
        dueDate: String(data.get("dueDate") ?? "").trim() || void 0,
        collaboratorId: String(data.get("collaboratorId") ?? "").trim() || void 0
      });
      setSummary((current) => current && { ...current, tasks: [...current.tasks, created], openTaskCount: current.openTaskCount + 1 });
      form.reset();
      setTitleError(false);
      setCreateOpen(false);
    } catch (error) {
      handleError(error);
    } finally {
      setMutationPending(false);
    }
  };
  const saveTask = async (event) => {
    event.preventDefault();
    if (!canWrite || !selectedTask) return;
    const data = new FormData(event.currentTarget);
    setMutationPending(true);
    try {
      const updated = await gateway.updateTask(selectedTask.id, {
        title: String(data.get("inspectorTitle") ?? "").trim() || selectedTask.title,
        notes: String(data.get("inspectorNotes") ?? ""),
        scheduledDate: String(data.get("inspectorScheduledDate") ?? "") || void 0,
        dueDate: String(data.get("inspectorDueDate") ?? "") || void 0
      });
      setSummary((current) => current && { ...current, tasks: current.tasks.map((task) => task.id === updated.id ? updated : task) });
      setSelectedTask(null);
    } catch (error) {
      handleError(error);
    } finally {
      setMutationPending(false);
    }
  };
  const updateInspectorCollaborator = async (collaboratorId) => {
    if (!canWrite || !selectedTask) return;
    try {
      const updated = await gateway.updateTask(selectedTask.id, { collaboratorId });
      setSelectedTask(updated);
      setSummary((current) => current && { ...current, tasks: current.tasks.map((task) => task.id === updated.id ? updated : task) });
    } catch (error) {
      handleError(error);
    }
  };
  return /* @__PURE__ */ jsxRuntime.jsx(ScreenRoot, { screenName: "Dashboard", testId: "rhythm-dashboard-screen", children: /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "page-shell pg-dashboard", "aria-busy": surfaceState === "loading", children: [
    /* @__PURE__ */ jsxRuntime.jsxs("header", { className: "dashboard-toolbar", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dashboard-heading", children: [
        /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Planning workspace" }),
        /* @__PURE__ */ jsxRuntime.jsx("h1", { children: "Dashboard" }),
        /* @__PURE__ */ jsxRuntime.jsx("p", { children: "A calm view of the week ahead." })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dashboard-header-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dashboard-summary-chips", "aria-label": "Dashboard summary", children: [
          /* @__PURE__ */ jsxRuntime.jsxs("span", { "data-testid": "dashboard-open-count", children: [
            summary?.openTaskCount ?? openCount,
            " open"
          ] }),
          /* @__PURE__ */ jsxRuntime.jsxs("span", { "data-testid": "dashboard-thread-count", children: [
            summary?.threadCount ?? 0,
            " threads"
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsx(HeaderTaskAction, { onClick: () => canWrite && setCreateOpen(true), disabled: !canWrite || !isContentVisible || mutationPending, testId: "dashboard-header-add-task" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "icon-button", type: "button", "aria-label": "Refresh dashboard", title: "Refresh dashboard", disabled: surfaceState === "loading", onClick: () => void load(), "data-testid": "dashboard-refresh", children: "\u21BB" })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "quick-card", "aria-labelledby": "dashboard-quick-title", children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Quick actions" }),
      /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "dashboard-quick-title", children: "Actions for the next task" }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { children: todayTasks[0]?.title ? `Prepare context for ${todayTasks[0].title}.` : "No task is next in queue yet." }),
      /* @__PURE__ */ jsxRuntime.jsx("div", { className: "quick-list", children: ["Help me finish this", "Draft next steps", "Summarize", "Create follow-up tasks"].map((label) => /* @__PURE__ */ jsxRuntime.jsx("button", { className: "action-chip", type: "button", onClick: () => host.onRequestFollowUp?.({ screen: "dashboard", label, relatedId: todayTasks[0]?.id }), "data-testid": `quick-action-${label.toLowerCase().replace(/[^a-z]+/g, "-")}`, children: label }, label)) })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dashboard-scroll", children: [
      !isContentVisible && /* @__PURE__ */ jsxRuntime.jsx(StatePanel2, { state: surfaceState, onRetry: () => void load(), onEmpty: () => canWrite && setCreateOpen(true), canWrite }),
      isContentVisible && summary && /* @__PURE__ */ jsxRuntime.jsxs(jsxRuntime.Fragment, { children: [
        !canWrite && /* @__PURE__ */ jsxRuntime.jsxs("p", { className: "inspector-prerequisite", role: "status", "data-testid": "dashboard-readonly-explanation", children: [
          /* @__PURE__ */ jsxRuntime.jsx("strong", { children: "Read-only workspace" }),
          /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Your host has not granted Dashboard write access. You can inspect work and ask Hermes, but changes are unavailable." })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "focus-shell", "aria-labelledby": "dashboard-focus-title", children: [
          /* @__PURE__ */ jsxRuntime.jsx("header", { className: "section-intro", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
            /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "At a glance" }),
            /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "dashboard-focus-title", children: "Focus for this week" }),
            /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Review today, the week ahead, and the next active project without leaving planning." })
          ] }) }),
          /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "focus-grid", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "progress-card", "data-testid": "today-progress", children: [
              /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "card-topline", children: [
                /* @__PURE__ */ jsxRuntime.jsx("h3", { children: "Today" }),
                /* @__PURE__ */ jsxRuntime.jsx("span", { children: todayDone === todayTasks.length ? "Clear" : `${todayTasks.length - todayDone} open` })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("dl", { className: "metrics-grid", children: [
                /* @__PURE__ */ jsxRuntime.jsx(Metric, { label: "Complete", value: todayDone }),
                /* @__PURE__ */ jsxRuntime.jsx(Metric, { label: "Open", value: todayTasks.length - todayDone }),
                /* @__PURE__ */ jsxRuntime.jsx(Metric, { label: "Next", value: todayTasks.find((task) => task.status === "open")?.title ?? "Clear" })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "deck-row", type: "button", onClick: () => host.onNavigateToScreen?.("planner"), "data-testid": "open-planner", children: [
                /* @__PURE__ */ jsxRuntime.jsx("strong", { children: todayTasks.find((task) => task.status === "open")?.title ?? "Today is clear" }),
                /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Open planner" })
              ] })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "progress-card", "data-testid": "week-progress", children: [
              /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "card-topline", children: [
                /* @__PURE__ */ jsxRuntime.jsx("h3", { children: "This week" }),
                /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-button", type: "button", onClick: () => host.onNavigateToScreen?.("planner"), "data-testid": "open-week-planner", children: "Open planner" })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("dl", { className: "metrics-grid", children: [
                /* @__PURE__ */ jsxRuntime.jsx(Metric, { label: "Open", value: weekTasks.length }),
                /* @__PURE__ */ jsxRuntime.jsx(Metric, { label: "Past due", value: pastDueTasks.length })
              ] })
            ] }),
            project && /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "progress-card", "data-testid": "project-progress", children: [
              /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "card-topline", children: [
                /* @__PURE__ */ jsxRuntime.jsx("h3", { children: project.title }),
                /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-button", type: "button", onClick: () => host.onNavigateToScreen?.("projects"), "data-testid": "open-projects", children: "Open projects" })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("p", { children: [
                "Owner ",
                project.owner,
                " \xB7 due ",
                project.dueLabel
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("dl", { className: "metrics-grid", children: [
                /* @__PURE__ */ jsxRuntime.jsx(Metric, { label: "Complete", value: projectDone }),
                /* @__PURE__ */ jsxRuntime.jsx(Metric, { label: "Open", value: projectSteps.length - projectDone }),
                /* @__PURE__ */ jsxRuntime.jsx(Metric, { label: "Next", value: projectNextStep?.title ?? "Clear" })
              ] }),
              projectNextStep ? /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "deck-row", type: "button", onClick: () => setSelectedStep(projectNextStep), "data-testid": "project-next-step", children: [
                /* @__PURE__ */ jsxRuntime.jsx("strong", { children: projectNextStep.title }),
                /* @__PURE__ */ jsxRuntime.jsx("span", { children: projectNextStep.dueLabel })
              ] }) : /* @__PURE__ */ jsxRuntime.jsx("div", { className: "deck-empty", children: "All project steps complete." })
            ] })
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsx("section", { className: "context-strip", "aria-label": "Dashboard handoffs", children: /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "unread-card", children: [
          /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "card-topline", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Unread context" }),
              /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Unread messages" })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsx("button", { className: "icon-button", type: "button", onClick: () => host.onNavigateToScreen?.("messages"), "aria-label": "Open messages", title: "Open messages", "data-testid": "open-messages", children: "\u2192" })
          ] }),
          summary.unreadThreads.length ? summary.unreadThreads.map((thread) => /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "thread-preview", type: "button", onClick: () => host.onNavigateToScreen?.("messages", { relatedId: thread.id }), "data-testid": `unread-preview-${thread.id}`, children: [
            /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("strong", { children: thread.title }),
              /* @__PURE__ */ jsxRuntime.jsx("small", { children: thread.preview })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("em", { children: [
              thread.unreadCount,
              " unread"
            ] })
          ] }, thread.id)) : /* @__PURE__ */ jsxRuntime.jsx("p", { className: "empty-copy", children: "No unread threads." })
        ] }) }),
        /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "planning-section", "aria-labelledby": "planning-title", children: [
          /* @__PURE__ */ jsxRuntime.jsx("header", { className: "section-intro compact", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
            /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Operational view" }),
            /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "planning-title", children: "Planning" }),
            /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Tasks stay grouped by urgency without losing collaborator or project context." })
          ] }) }),
          /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "planning-grid", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "planning-card wide", "data-testid": "planning-past-due", children: [
              /* @__PURE__ */ jsxRuntime.jsx("div", { className: "list-head", children: /* @__PURE__ */ jsxRuntime.jsxs("h3", { children: [
                "Past due \xB7 ",
                pastDueTasks.length
              ] }) }),
              pastDueTasks.map((task) => /* @__PURE__ */ jsxRuntime.jsx(TaskEntry, { task, readonly: !canWrite || mutationPending, onInspect: setSelectedTask, onToggle: (item) => void toggleTask(item) }, task.id)),
              !pastDueTasks.length && /* @__PURE__ */ jsxRuntime.jsx("p", { className: "empty-copy", children: "Nothing overdue." })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "planning-card", "data-testid": "planning-handoffs", children: [
              /* @__PURE__ */ jsxRuntime.jsx("div", { className: "list-head", children: /* @__PURE__ */ jsxRuntime.jsx("h3", { children: "Collaborator handoffs" }) }),
              handoffTasks.length ? handoffTasks.map((task) => /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "handoff-row", children: [
                /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
                  /* @__PURE__ */ jsxRuntime.jsx("strong", { children: task.title }),
                  /* @__PURE__ */ jsxRuntime.jsx("small", { children: task.collaboratorName })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsx("em", { children: task.dueLabel })
              ] }, task.id)) : /* @__PURE__ */ jsxRuntime.jsx("p", { className: "empty-copy", children: "No collaborator handoffs." })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "planning-card", "data-testid": "planning-today", children: [
              /* @__PURE__ */ jsxRuntime.jsx("div", { className: "list-head", children: /* @__PURE__ */ jsxRuntime.jsxs("h3", { children: [
                "Today \xB7 ",
                todayTasks.length
              ] }) }),
              todayTasks.map((task) => /* @__PURE__ */ jsxRuntime.jsx(TaskEntry, { task, readonly: !canWrite || mutationPending, onInspect: setSelectedTask, onToggle: (item) => void toggleTask(item) }, task.id))
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "planning-card", "data-testid": "planning-week", children: [
              /* @__PURE__ */ jsxRuntime.jsx("div", { className: "list-head", children: /* @__PURE__ */ jsxRuntime.jsxs("h3", { children: [
                "This week \xB7 ",
                weekTasks.length
              ] }) }),
              weekTasks.map((task) => /* @__PURE__ */ jsxRuntime.jsx(TaskEntry, { task, readonly: !canWrite || mutationPending, onInspect: setSelectedTask, onToggle: (item) => void toggleTask(item) }, task.id)),
              !weekTasks.length && /* @__PURE__ */ jsxRuntime.jsx("p", { className: "empty-copy", children: "No open tasks later this week." })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "planning-card", "data-testid": "planning-project-steps", children: [
              /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "list-head", children: [
                /* @__PURE__ */ jsxRuntime.jsx("h3", { children: "Project on deck" }),
                /* @__PURE__ */ jsxRuntime.jsx("span", { children: projectSteps.filter((step) => step.status === "open").length })
              ] }),
              projectSteps.map((step) => /* @__PURE__ */ jsxRuntime.jsx(ProjectStepEntry, { step, readonly: !canWrite || mutationPending, onInspect: setSelectedStep, onToggle: (item) => void toggleStep(item) }, step.id)),
              !projectSteps.length && /* @__PURE__ */ jsxRuntime.jsx("p", { className: "empty-copy", children: "All project steps are complete." })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "planning-card wide", "data-testid": "planning-unscheduled", children: [
              /* @__PURE__ */ jsxRuntime.jsx("div", { className: "list-head", children: /* @__PURE__ */ jsxRuntime.jsxs("h3", { children: [
                "Unscheduled \xB7 ",
                unscheduledTasks.length
              ] }) }),
              unscheduledTasks.map((task) => /* @__PURE__ */ jsxRuntime.jsx(TaskEntry, { task, readonly: !canWrite || mutationPending, onInspect: setSelectedTask, onToggle: (item) => void toggleTask(item) }, task.id)),
              !unscheduledTasks.length && /* @__PURE__ */ jsxRuntime.jsx("p", { className: "empty-copy", children: "Every open task has a date." })
            ] })
          ] })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: createOpen, onClose: () => {
      setCreateOpen(false);
      setTitleError(false);
    }, title: "Add task", description: "Set the task details now.", testId: "dashboard-task-create", children: /* @__PURE__ */ jsxRuntime.jsx(
      TaskCreateForm,
      {
        idPrefix: "dashboard-create",
        onSubmit: createTask,
        onCancel: () => {
          setCreateOpen(false);
          setTitleError(false);
        },
        members,
        titleRef: taskTitleRef,
        titleError: titleError ? "Enter a task title." : void 0,
        onTitleChange: () => setTitleError(false),
        disabled: !canWrite || mutationPending,
        noValidate: true,
        testIds: { title: "task-title", notes: "task-notes", scheduledDate: "task-schedule", dueDate: "task-due-date", collaborator: "task-collaborator", cancel: "dashboard-task-create-cancel", submit: "task-add", error: "task-title-error" }
      }
    ) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(selectedTask), onClose: () => setSelectedTask(null), title: "Task details", description: "Inspect or update the selected task.", testId: "task-inspector", wide: true, children: /* @__PURE__ */ jsxRuntime.jsx("form", { className: "inspector-form", onSubmit: saveTask, children: /* @__PURE__ */ jsxRuntime.jsxs("fieldset", { disabled: !canWrite || mutationPending, children: [
      /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
        "Task title",
        /* @__PURE__ */ jsxRuntime.jsx("input", { disabled: !canWrite || mutationPending, name: "inspectorTitle", defaultValue: selectedTask?.title ?? "", "data-autofocus": true, "data-testid": "task-inspector-title" })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
        "Notes",
        /* @__PURE__ */ jsxRuntime.jsx("textarea", { disabled: !canWrite || mutationPending, name: "inspectorNotes", defaultValue: selectedTask?.notes ?? "", rows: 4, "data-testid": "task-inspector-notes" })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "inspector-pair", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
          "Scheduled date",
          /* @__PURE__ */ jsxRuntime.jsx("input", { disabled: !canWrite || mutationPending, name: "inspectorScheduledDate", type: "date", defaultValue: selectedTask?.scheduledDate ?? "", "data-testid": "task-inspector-scheduled" })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
          "Due date",
          /* @__PURE__ */ jsxRuntime.jsx("input", { disabled: !canWrite || mutationPending, name: "inspectorDueDate", type: "date", defaultValue: selectedTask?.dueDate ?? "", "data-testid": "task-inspector-due" })
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "inspector-collaborator", "aria-label": "Task collaborator", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
          /* @__PURE__ */ jsxRuntime.jsx("strong", { children: "Collaborator" }),
          /* @__PURE__ */ jsxRuntime.jsx("small", { children: selectedTask?.collaboratorName ?? "No collaborator assigned" })
        ] }),
        selectedTask?.collaboratorId ? /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-danger-button", type: "button", disabled: !canWrite || mutationPending, onClick: () => void updateInspectorCollaborator(null), "data-testid": "task-inspector-collaborator-remove", children: "Remove" }) : /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "secondary-button", type: "button", disabled: !canWrite || mutationPending || !members[0], onClick: () => members[0] && void updateInspectorCollaborator(members[0].id), "data-testid": "task-inspector-collaborator-add", children: [
          "Add ",
          members[0]?.name ?? "collaborator"
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("footer", { children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => setSelectedTask(null), "data-testid": "task-inspector-cancel", children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "submit", disabled: !canWrite || mutationPending, "data-testid": "task-inspector-save", children: "Save changes" })
      ] })
    ] }) }) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(selectedStep), onClose: () => setSelectedStep(null), title: "Project step details", description: project ? `${project.title} \xB7 project step` : "Project step", testId: "project-step-inspector", wide: true, children: /* @__PURE__ */ jsxRuntime.jsx("form", { className: "inspector-form", onSubmit: (event) => {
      event.preventDefault();
      if (canWrite) setSelectedStep(null);
    }, children: /* @__PURE__ */ jsxRuntime.jsxs("fieldset", { disabled: !canWrite || mutationPending, children: [
      /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
        "Step title",
        /* @__PURE__ */ jsxRuntime.jsx("input", { name: "stepTitle", defaultValue: selectedStep?.title ?? "", "data-autofocus": true, "data-testid": "project-step-title" })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
        "Notes",
        /* @__PURE__ */ jsxRuntime.jsx("textarea", { name: "stepNotes", defaultValue: selectedStep?.notes ?? "", rows: 3, "data-testid": "project-step-notes" })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("footer", { children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => setSelectedStep(null), "data-testid": "project-step-cancel", children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "submit", "data-testid": "project-step-save", children: "Save changes" })
      ] })
    ] }) }) })
  ] }) });
}
var ANCHOR = "2026-08-12";
var MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function addDaysIso(iso, days) {
  const date = /* @__PURE__ */ new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
function formatIsoDate(iso) {
  const parts = iso.split("-").map(Number);
  const year = parts[0] ?? 0;
  const month = parts[1] ?? 1;
  const day = parts[2] ?? 1;
  return `${MONTH_NAMES[month - 1]} ${day}, ${year}`;
}
function computeRange(mode, offset) {
  if (mode === "day") {
    const day = addDaysIso(ANCHOR, offset);
    return { start: day, end: day, label: formatIsoDate(day) };
  }
  if (mode === "week") {
    const anchorDow = (/* @__PURE__ */ new Date(`${ANCHOR}T00:00:00Z`)).getUTCDay();
    const mondayOffset = anchorDow === 0 ? -6 : 1 - anchorDow;
    const monday = addDaysIso(ANCHOR, mondayOffset + offset * 7);
    const sunday = addDaysIso(monday, 6);
    return { start: monday, end: sunday, label: `${formatIsoDate(monday)} \u2013 ${formatIsoDate(sunday)}` };
  }
  const anchorDate = /* @__PURE__ */ new Date(`${ANCHOR}T00:00:00Z`);
  const monthStart = new Date(Date.UTC(anchorDate.getUTCFullYear(), anchorDate.getUTCMonth() + offset, 1));
  const monthEnd = new Date(Date.UTC(monthStart.getUTCFullYear(), monthStart.getUTCMonth() + 1, 0));
  return {
    start: monthStart.toISOString().slice(0, 10),
    end: monthEnd.toISOString().slice(0, 10),
    label: `${MONTH_NAMES[monthStart.getUTCMonth()]} ${monthStart.getUTCFullYear()}`
  };
}
function dateOnly(value) {
  return value.slice(0, 10);
}
function timeOnly(value) {
  return value.slice(11, 16);
}
function displayTime(value) {
  const [hourText, minute] = timeOnly(value).split(":");
  const hour = Number(hourText);
  return `${hour % 12 || 12}:${minute} ${hour >= 12 ? "PM" : "AM"}`;
}
function slug(value) {
  return value.toLocaleLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "unassigned";
}
function ActionMenu({ label, testId, children }) {
  const [open, setOpen] = react.useState(false);
  const rootRef = react.useRef(null);
  const triggerRef = react.useRef(null);
  react.useEffect(() => {
    if (!open) return;
    const closeOutside = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    };
    const closeWithEscape = (event) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener("mousedown", closeOutside);
    document.addEventListener("keydown", closeWithEscape);
    requestAnimationFrame(() => rootRef.current?.querySelector('[role="menuitem"]:not([disabled])')?.focus());
    return () => {
      document.removeEventListener("mousedown", closeOutside);
      document.removeEventListener("keydown", closeWithEscape);
    };
  }, [open]);
  const moveFocus = (event) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const items = [...event.currentTarget.querySelectorAll('[role="menuitem"]:not([disabled])')];
    if (!items.length) return;
    event.preventDefault();
    const current = Math.max(0, items.indexOf(document.activeElement));
    const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (current + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    items[next]?.focus();
  };
  return /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-menu-anchor", ref: rootRef, children: [
    /* @__PURE__ */ jsxRuntime.jsx("button", { ref: triggerRef, className: "icon-button", type: "button", "aria-label": label, "aria-haspopup": "menu", "aria-expanded": open, onClick: () => setOpen((value) => !value), "data-testid": testId, children: /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "more", size: 16 }) }),
    open && /* @__PURE__ */ jsxRuntime.jsx("div", { className: "menu-popover facilities-menu", role: "menu", "aria-label": label, onKeyDown: moveFocus, onClick: () => setOpen(false), children })
  ] });
}
function StatePanel3({ state, onRetry }) {
  if (state === "loading") {
    return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "facilities-state", role: "status", "aria-live": "polite", "data-testid": "page-state-loading", children: [
      /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Loading facilities" }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Gathering rooms and the current reservation schedule." })
    ] });
  }
  if (state === "empty") {
    return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "facilities-state", role: "status", "data-testid": "page-state-empty", children: [
      /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "No facilities yet" }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Add the first space to make room reservations available to this workspace." })
    ] });
  }
  if (state === "server_error") {
    return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "facilities-state danger", role: "alert", "data-testid": "page-state-server-error", children: [
      /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Facilities could not be loaded" }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { children: "The schedule service returned a temporary error." }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
    ] });
  }
  if (state === "forbidden") {
    return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "facilities-state warning", role: "alert", "data-testid": "page-state-forbidden", children: [
      /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Workspace access required" }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Join an authenticated Rhythm workspace before inspecting its facilities." })
    ] });
  }
  return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "facilities-state warning", role: "status", "data-testid": "page-state-unavailable", children: [
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Facilities are unavailable" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Reconnect the facilities service before loading or changing this schedule." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
  ] });
}
function FacilitiesScreen() {
  const { facilities: gateway } = useRhythmDomainGateway();
  const host = useRhythmHost();
  const [surfaceState, setSurfaceState] = react.useState("loading");
  const [facilities, setFacilities] = react.useState([]);
  const [reservations, setReservations] = react.useState([]);
  const [mode, setMode] = react.useState("overview");
  const [rangeMode, setRangeMode] = react.useState("week");
  const [rangeOffset, setRangeOffset] = react.useState(0);
  const [buildingFilter, setBuildingFilter] = react.useState("");
  const [roomFilter, setRoomFilter] = react.useState("");
  const [selectedReservationId, setSelectedReservationId] = react.useState(null);
  const [selectedRoomId, setSelectedRoomId] = react.useState(null);
  const [reservationDialogOpen, setReservationDialogOpen] = react.useState(false);
  const [editingReservation, setEditingReservation] = react.useState(null);
  const [formRoomId, setFormRoomId] = react.useState("");
  const [formTitle, setFormTitle] = react.useState("");
  const [formRequesterName, setFormRequesterName] = react.useState("");
  const [formDate, setFormDate] = react.useState("");
  const [formStart, setFormStart] = react.useState("");
  const [formEnd, setFormEnd] = react.useState("");
  const [formNotes, setFormNotes] = react.useState("");
  const [formErrors, setFormErrors] = react.useState({});
  const [deleteReservationTarget, setDeleteReservationTarget] = react.useState(null);
  const [deleteSeriesTarget, setDeleteSeriesTarget] = react.useState(null);
  const [deleteGroupTarget, setDeleteGroupTarget] = react.useState(null);
  const [facilityEditorOpen, setFacilityEditorOpen] = react.useState(false);
  const [editingFacility, setEditingFacility] = react.useState(null);
  const [facilityName, setFacilityName] = react.useState("");
  const [facilityBuilding, setFacilityBuilding] = react.useState("");
  const [newBuilding, setNewBuilding] = react.useState("");
  const [facilityDescription, setFacilityDescription] = react.useState("");
  const [facilityNameError, setFacilityNameError] = react.useState("");
  const [deleteFacilityTarget, setDeleteFacilityTarget] = react.useState(null);
  const [operationTarget, setOperationTarget] = react.useState(null);
  const [automationOpen, setAutomationOpen] = react.useState(false);
  const [automationRoom, setAutomationRoom] = react.useState("");
  const [automationStart, setAutomationStart] = react.useState("");
  const [automationEnd, setAutomationEnd] = react.useState("");
  const [mutationPending, setMutationPending] = react.useState(false);
  const [mutationNotice, setMutationNotice] = react.useState("");
  const requestGeneration = react.useRef(0);
  const operationGeneration = react.useRef(0);
  const operationEpoch = react.useRef(0);
  const currentRange = computeRange(rangeMode, rangeOffset);
  const handleError = (error) => {
    const kind = error instanceof RhythmGatewayError ? error.kind : "server_error";
    setSurfaceState(kind === "forbidden" ? "forbidden" : kind === "not_found" ? "unavailable" : kind === "unavailable" ? "unavailable" : "server_error");
  };
  const capabilities = host.currentUser.capabilities ?? [];
  const canManage = capabilities.includes("facilities.manage");
  const can = (operation) => canManage || capabilities.includes(operation);
  const canReserve = can("facilities.create-reservation") || capabilities.includes("facilities.reserve");
  const canEditReservation = (reservation, operation) => Boolean(reservation && (canManage || (capabilities.includes("facilities.reserve") || capabilities.includes(operation)) && reservation.creatorId === host.currentUser.id));
  const canSubmitReservation = editingReservation ? canEditReservation(editingReservation, editingReservation.groupId ? "facilities.update-group" : "facilities.update-reservation") : canReserve;
  const mutationExplanation = canManage || canReserve ? "" : "You can inspect this schedule, but a Facilities manager must grant reservation access.";
  const queueOperation = (operation, entityId, payload, mutate) => {
    if (!can(operation) && !(operation === "facilities.create-reservation" && capabilities.includes("facilities.reserve"))) return;
    operationGeneration.current += 1;
    operationEpoch.current += 1;
    setOperationTarget({ operation, entityId, payload, mutate, generation: `${entityId}:${operation}:${operationGeneration.current}` });
  };
  const cancelOperation = () => {
    operationEpoch.current += 1;
    setOperationTarget(null);
  };
  const confirmOperation = async () => {
    const target = operationTarget;
    if (!target || mutationPending) return;
    const epoch = operationEpoch.current;
    setMutationPending(true);
    try {
      const confirmation = { operation: target.operation, entityId: target.entityId, payload: target.payload, generation: target.generation };
      if (host.confirmWorkspaceOperation && !await host.confirmWorkspaceOperation(confirmation)) return;
      if (operationEpoch.current !== epoch) return;
      await target.mutate();
      if (operationEpoch.current !== epoch) return;
      setOperationTarget(null);
    } catch (error) {
      handleError(error);
    } finally {
      setMutationPending(false);
    }
  };
  const load = async (range = currentRange) => {
    const generation = ++requestGeneration.current;
    setSurfaceState("loading");
    try {
      const [loadedFacilities, loadedReservations] = await Promise.all([gateway.facilities(), gateway.reservations({ start: `${range.start}T00:00:00.000`, end: `${range.end}T23:59:59.999` })]);
      if (generation !== requestGeneration.current) return;
      setFacilities(loadedFacilities);
      setReservations(loadedReservations);
      setSurfaceState(loadedFacilities.length ? "ready" : "empty");
    } catch (error) {
      if (generation !== requestGeneration.current) return;
      handleError(error);
    }
  };
  react.useEffect(() => {
    void load(currentRange);
    return () => {
      requestGeneration.current += 1;
    };
  }, [gateway, rangeMode, rangeOffset]);
  const showsWorkspace = surfaceState === "ready";
  const visibleReservations = reservations.filter((reservation) => !reservation.automation).filter((reservation) => {
    const facility = facilities.find((item) => item.id === reservation.facilityId);
    if (!facility) return false;
    if (buildingFilter && facility.building !== buildingFilter) return false;
    if (roomFilter && reservation.facilityId !== roomFilter) return false;
    const date = dateOnly(reservation.start);
    return date >= currentRange.start && date <= currentRange.end;
  }).sort((left, right) => left.start.localeCompare(right.start));
  const roomsInUse = new Set(visibleReservations.map((reservation) => reservation.facilityId)).size;
  const setupNotesCount = visibleReservations.filter((reservation) => reservation.notes).length;
  const conflictsCount = visibleReservations.filter((reservation) => reservation.conflicted).length;
  const selectedReservation = reservations.find((reservation) => reservation.id === selectedReservationId) ?? null;
  const selectedRoom = facilities.find((facility) => facility.id === selectedRoomId) ?? null;
  const buildings = [...new Set(facilities.map((facility) => facility.building).filter((value) => Boolean(value)))].sort();
  const groupedFacilities = [...buildings, null].map((building) => ({
    building,
    facilities: facilities.filter((facility) => facility.building === building).sort((left, right) => left.name.localeCompare(right.name))
  })).filter((group) => group.facilities.length > 0);
  const clearFilters = () => {
    setRangeMode("week");
    setRangeOffset(0);
    setBuildingFilter("");
    setRoomFilter("");
  };
  const openReservationEditor = (reservation, presetFacilityId) => {
    setEditingReservation(reservation);
    setFormRoomId(reservation?.facilityId ?? presetFacilityId ?? facilities[0]?.id ?? "");
    setFormTitle(reservation?.title ?? "");
    setFormRequesterName(reservation?.requesterName ?? host.currentUser.displayName);
    setFormDate(reservation ? dateOnly(reservation.start) : currentRange.start);
    setFormStart(reservation ? timeOnly(reservation.start) : "");
    setFormEnd(reservation ? timeOnly(reservation.end) : "");
    setFormNotes(reservation?.notes ?? "");
    setFormErrors({});
    setReservationDialogOpen(true);
  };
  const closeReservationEditor = () => {
    setReservationDialogOpen(false);
    setEditingReservation(null);
    setFormErrors({});
  };
  const formConflicts = formStart && formEnd ? reservations.filter((reservation) => reservation.facilityId === formRoomId && !reservation.automation && reservation.id !== editingReservation?.id && dateOnly(reservation.start) === formDate && timeOnly(reservation.start) < formEnd && timeOnly(reservation.end) > formStart) : [];
  const availabilityText = !formStart || !formEnd ? "Choose a start and end time" : formConflicts.length ? `${formConflicts.length} reservation${formConflicts.length === 1 ? "" : "s"} overlap the selected slot` : "Selected slot is open";
  const submitReservation = async (event) => {
    event.preventDefault();
    if (!canSubmitReservation) return;
    const errors = {};
    if (!formRoomId) errors.room = "Select a room";
    if (!formTitle.trim()) errors.title = "Title is required";
    if (!formDate || !formStart || !formEnd) errors.slot = "Choose a date, start time, and end time";
    else if (formEnd <= formStart) errors.slot = "End time must be after the start time";
    else if (!editingReservation && formConflicts.length) errors.slot = `${formTitle || "This reservation"} overlaps an existing reservation`;
    setFormErrors(errors);
    if (Object.keys(errors).length) return;
    const start = `${formDate}T${formStart}:00-07:00`;
    const end = `${formDate}T${formEnd}:00-07:00`;
    const input = { title: formTitle.trim(), requesterName: formRequesterName.trim() || host.currentUser.displayName, start, end, notes: formNotes || null };
    if (editingReservation?.groupId) {
      queueOperation("facilities.update-group", editingReservation.groupId, input, async () => {
        const updated = await gateway.updateGroup(editingReservation.groupId, input);
        setReservations((current) => current.map((reservation) => updated.find((item) => item.id === reservation.id) ?? reservation));
        closeReservationEditor();
      });
    } else if (editingReservation) {
      queueOperation("facilities.update-reservation", editingReservation.id, input, async () => {
        const updated = await gateway.updateReservation(editingReservation.id, input);
        setReservations((current) => current.map((reservation) => reservation.id === updated.id ? updated : reservation));
        closeReservationEditor();
      });
    } else {
      const createInput = { facilityId: formRoomId, ...input };
      queueOperation("facilities.create-reservation", "new-reservation", createInput, async () => {
        const created = await gateway.createReservation(createInput);
        setReservations((current) => [...current, created]);
        closeReservationEditor();
      });
    }
  };
  const confirmDeleteReservation = async () => {
    if (!deleteReservationTarget) return;
    if (!canEditReservation(deleteReservationTarget, "facilities.delete-reservation")) return;
    const target = deleteReservationTarget;
    setDeleteReservationTarget(null);
    queueOperation("facilities.delete-reservation", target.id, {}, async () => {
      await gateway.deleteReservation(target.id);
      setReservations((current) => current.filter((reservation) => reservation.id !== target.id));
      if (selectedReservationId === target.id) setSelectedReservationId(null);
    });
  };
  const confirmDeleteSeries = async () => {
    if (!deleteSeriesTarget?.seriesId) return;
    if (!can("facilities.delete-series")) return;
    const target = deleteSeriesTarget;
    setDeleteSeriesTarget(null);
    queueOperation("facilities.delete-series", target.seriesId, {}, async () => {
      const result = await gateway.deleteSeries(target.seriesId);
      setMutationNotice(`${result.deletedCount} recurring reservations were deleted. The schedule was reloaded.`);
      await load();
      setSelectedReservationId(null);
    });
  };
  const confirmDeleteGroup = async () => {
    if (!deleteGroupTarget?.groupId || !canEditReservation(deleteGroupTarget, "facilities.delete-group")) return;
    const target = deleteGroupTarget;
    setDeleteGroupTarget(null);
    queueOperation("facilities.delete-group", target.groupId, {}, async () => {
      const result = await gateway.deleteGroup(target.groupId);
      setMutationNotice(`${result.deletedCount} linked reservations were deleted. The schedule was reloaded.`);
      await load();
      setSelectedReservationId(null);
    });
  };
  const openFacilityEditor = (facility) => {
    setEditingFacility(facility);
    setFacilityName(facility?.name ?? "");
    setFacilityBuilding(facility?.building ?? "");
    setNewBuilding("");
    setFacilityDescription(facility?.description ?? "");
    setFacilityNameError("");
    setFacilityEditorOpen(true);
  };
  const closeFacilityEditor = () => setFacilityEditorOpen(false);
  const submitFacility = async (event) => {
    event.preventDefault();
    if (!(editingFacility ? can("facilities.update-facility") : can("facilities.create-facility"))) return;
    if (!facilityName.trim()) {
      setFacilityNameError("Room name is required");
      return;
    }
    const building = facilityBuilding === "__new_building__" ? newBuilding.trim() : facilityBuilding;
    const input = { name: facilityName.trim(), building: building || null, description: facilityDescription.trim() };
    if (editingFacility) queueOperation("facilities.update-facility", editingFacility.id, input, async () => {
      const updated = await gateway.updateFacility(editingFacility.id, input);
      setFacilities((current) => current.map((facility) => facility.id === updated.id ? updated : facility));
      setFacilityEditorOpen(false);
    });
    else queueOperation("facilities.create-facility", "new-facility", input, async () => {
      const created = await gateway.createFacility(input);
      setFacilities((current) => [...current, created]);
      setFacilityEditorOpen(false);
    });
  };
  const confirmDeleteFacility = async () => {
    if (!deleteFacilityTarget) return;
    if (!can("facilities.delete-facility")) return;
    const target = deleteFacilityTarget;
    setDeleteFacilityTarget(null);
    queueOperation("facilities.delete-facility", target.id, {}, async () => {
      await gateway.deleteFacility(target.id);
      setFacilities((current) => current.filter((facility) => facility.id !== target.id));
      setReservations((current) => current.filter((reservation) => reservation.facilityId !== target.id));
      if (selectedRoomId === target.id) setSelectedRoomId(null);
    });
  };
  const filteredAutomation = reservations.filter((reservation) => {
    if (!reservation.automation) return false;
    if (automationRoom && reservation.facilityId !== automationRoom) return false;
    const date = dateOnly(reservation.start);
    if (automationStart && date < automationStart) return false;
    if (automationEnd && date > automationEnd) return false;
    return true;
  });
  const openAutomation = () => {
    setAutomationRoom("");
    setAutomationStart("");
    setAutomationEnd("");
    setAutomationOpen(true);
  };
  const cleanupAutomation = async () => {
    const targets = filteredAutomation.map((reservation) => reservation.id);
    if (!can("facilities.delete-reservations")) return;
    queueOperation("facilities.delete-reservations", "automation-reservations", { ids: targets }, async () => {
      setMutationNotice("");
      if (gateway.deleteReservations) {
        const result = await gateway.deleteReservations(targets);
        if (result.deletedIds.length !== targets.length) setMutationNotice(`${result.deletedIds.length} of ${targets.length} automation reservations were deleted. The schedule was reloaded.`);
      } else {
        const results = await Promise.allSettled(targets.map((id) => gateway.deleteReservation(id)));
        const failed = results.filter((result) => result.status === "rejected").length;
        if (failed) setMutationNotice(`${targets.length - failed} of ${targets.length} automation reservations were deleted. The schedule was reloaded.`);
      }
      await load();
      setAutomationOpen(false);
    });
  };
  return /* @__PURE__ */ jsxRuntime.jsx(ScreenRoot, { screenName: "Facilities", testId: "rhythm-facilities-screen", children: /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "page-shell pg-facilities", "aria-busy": surfaceState === "loading", children: [
    /* @__PURE__ */ jsxRuntime.jsxs("header", { className: "facilities-header", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-heading", children: [
        /* @__PURE__ */ jsxRuntime.jsx("h1", { children: "Facilities" }),
        /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Coordinate rooms and setup-sensitive reservations." })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("fieldset", { className: "facilities-mutation-gate", disabled: !showsWorkspace || mutationPending || !canReserve, children: [
        /* @__PURE__ */ jsxRuntime.jsx("legend", { className: "sr-only", children: "Facilities actions" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", disabled: !canReserve, onClick: () => openReservationEditor(null), "data-testid": "facilities-reserve-space", children: "Reserve Space" })
      ] }),
      !canReserve && /* @__PURE__ */ jsxRuntime.jsx("p", { className: "facilities-read-only", role: "status", "data-testid": "facilities-read-only", children: mutationExplanation })
    ] }),
    mutationNotice && /* @__PURE__ */ jsxRuntime.jsx("p", { role: "alert", "data-testid": "facilities-mutation-notice", children: mutationNotice }),
    !showsWorkspace && /* @__PURE__ */ jsxRuntime.jsx(StatePanel3, { state: surfaceState, onRetry: () => void load() }),
    showsWorkspace && /* @__PURE__ */ jsxRuntime.jsxs(jsxRuntime.Fragment, { children: [
      /* @__PURE__ */ jsxRuntime.jsxs("nav", { className: "facilities-mode-switch", "aria-label": "Facilities views", children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { type: "button", "aria-pressed": mode === "overview", onClick: () => setMode("overview"), "data-testid": "facilities-mode-overview", children: "Overview" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { type: "button", "aria-pressed": mode === "rooms", onClick: () => setMode("rooms"), "data-testid": "facilities-mode-rooms", children: "Rooms" })
      ] }),
      mode === "overview" ? /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-split-shell", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-list-pane", children: [
          /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "facilities-command-deck", "aria-label": "Schedule range and filters", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-range-controls", children: [
              /* @__PURE__ */ jsxRuntime.jsx("div", { className: "facilities-segmented", "aria-label": "Schedule range", children: ["day", "week", "month"].map((range) => /* @__PURE__ */ jsxRuntime.jsx("button", { type: "button", "aria-pressed": rangeMode === range, onClick: () => {
                setRangeMode(range);
                setRangeOffset(0);
              }, "data-testid": `facilities-range-${range}`, children: range.charAt(0).toUpperCase() + range.slice(1) }, range)) }),
              /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-period-nav", children: [
                /* @__PURE__ */ jsxRuntime.jsx("button", { className: "icon-button", type: "button", "aria-label": "Previous range", onClick: () => setRangeOffset((value) => value - 1), "data-testid": "facilities-range-back", children: /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "chevronRight", size: 14, style: { transform: "rotate(180deg)" } }) }),
                /* @__PURE__ */ jsxRuntime.jsx("strong", { "data-testid": "facilities-range-label", children: currentRange.label }),
                /* @__PURE__ */ jsxRuntime.jsx("button", { className: "icon-button", type: "button", "aria-label": "Next range", onClick: () => setRangeOffset((value) => value + 1), "data-testid": "facilities-range-forward", children: /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "chevronRight", size: 14 }) })
              ] })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-filter-row", children: [
              /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
                "Building",
                /* @__PURE__ */ jsxRuntime.jsxs("select", { value: buildingFilter, onChange: (event) => {
                  setBuildingFilter(event.target.value);
                }, "data-testid": "facilities-building-filter", children: [
                  /* @__PURE__ */ jsxRuntime.jsx("option", { value: "", children: "All buildings" }),
                  buildings.map((building) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: building, children: building }, building))
                ] })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
                "Room",
                /* @__PURE__ */ jsxRuntime.jsxs("select", { value: roomFilter, onChange: (event) => setRoomFilter(event.target.value), "data-testid": "facilities-room-filter", children: [
                  /* @__PURE__ */ jsxRuntime.jsx("option", { value: "", children: "All rooms" }),
                  facilities.filter((facility) => !buildingFilter || facility.building === buildingFilter).map((facility) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: facility.id, children: facility.name }, facility.id))
                ] })
              ] })
            ] })
          ] }),
          /* @__PURE__ */ jsxRuntime.jsxs("dl", { className: "facilities-metrics", "aria-label": "Reservation indicators", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Reservations" }),
              /* @__PURE__ */ jsxRuntime.jsx("dd", { "data-testid": "facilities-metric-reservations", children: visibleReservations.length })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Rooms in use" }),
              /* @__PURE__ */ jsxRuntime.jsx("dd", { "data-testid": "facilities-metric-rooms-in-use", children: roomsInUse })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Setup" }),
              /* @__PURE__ */ jsxRuntime.jsx("dd", { "data-testid": "facilities-metric-setup-notes", children: setupNotesCount })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Conflicts" }),
              /* @__PURE__ */ jsxRuntime.jsx("dd", { "data-testid": "facilities-metric-conflicts", children: conflictsCount })
            ] })
          ] }),
          /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "facilities-schedule", "aria-labelledby": "facilities-schedule-title", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "facilities-schedule-title", children: "Schedule" }),
              /* @__PURE__ */ jsxRuntime.jsxs("p", { children: [
                visibleReservations.length,
                " visible reservation",
                visibleReservations.length === 1 ? "" : "s"
              ] })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsx("div", { className: "facilities-reservation-list", "data-testid": "facilities-overview-results", children: visibleReservations.length ? visibleReservations.map((reservation) => {
              const facility = facilities.find((item) => item.id === reservation.facilityId);
              return /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "facilities-reservation-row", "aria-current": selectedReservationId === reservation.id ? "true" : void 0, "data-testid": `facility-reservation-${reservation.id}`, children: [
                /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "facilities-reservation-open", type: "button", onClick: () => setSelectedReservationId(reservation.id), "data-testid": `facility-reservation-open-${reservation.id}`, children: [
                  /* @__PURE__ */ jsxRuntime.jsxs("time", { dateTime: reservation.start, children: [
                    /* @__PURE__ */ jsxRuntime.jsx("strong", { children: displayTime(reservation.start) }),
                    /* @__PURE__ */ jsxRuntime.jsx("span", { children: displayTime(reservation.end) })
                  ] }),
                  /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "facilities-reservation-copy", children: [
                    /* @__PURE__ */ jsxRuntime.jsx("strong", { children: reservation.title }),
                    /* @__PURE__ */ jsxRuntime.jsxs("small", { children: [
                      facility?.name,
                      " \xB7 ",
                      facility?.building ?? "Unassigned",
                      " \xB7 ",
                      reservation.requesterName
                    ] })
                  ] }),
                  /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "facilities-badges", children: [
                    reservation.seriesId && /* @__PURE__ */ jsxRuntime.jsx("em", { children: "Series" }),
                    reservation.groupId && /* @__PURE__ */ jsxRuntime.jsx("em", { children: "Group" }),
                    reservation.notes && /* @__PURE__ */ jsxRuntime.jsx("em", { children: "Setup" }),
                    reservation.external && /* @__PURE__ */ jsxRuntime.jsx("em", { children: "External" }),
                    reservation.conflicted && /* @__PURE__ */ jsxRuntime.jsx("em", { className: "danger", children: "Conflict" })
                  ] })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsxs(ActionMenu, { label: `Actions for ${reservation.title}`, testId: `facility-reservation-menu-${reservation.id}`, children: [
                  /* @__PURE__ */ jsxRuntime.jsx("button", { className: "menu-item", role: "menuitem", type: "button", disabled: !canEditReservation(reservation, reservation.groupId ? "facilities.update-group" : "facilities.update-reservation"), onClick: () => openReservationEditor(reservation), "data-testid": `facility-reservation-menu-edit-${reservation.id}`, children: reservation.groupId ? "Edit linked group" : "Edit reservation" }),
                  /* @__PURE__ */ jsxRuntime.jsx("button", { className: "menu-item danger-item", role: "menuitem", type: "button", disabled: reservation.seriesId ? !can("facilities.delete-series") : !canEditReservation(reservation, reservation.groupId ? "facilities.delete-group" : "facilities.delete-reservation"), onClick: () => reservation.seriesId ? setDeleteSeriesTarget(reservation) : reservation.groupId ? setDeleteGroupTarget(reservation) : setDeleteReservationTarget(reservation), "data-testid": `facility-reservation-menu-delete-${reservation.id}`, children: reservation.seriesId ? "Delete series" : reservation.groupId ? "Delete linked group" : "Delete reservation" })
                ] })
              ] }, reservation.id);
            }) : /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-local-empty", role: "status", "data-testid": "facilities-no-results", children: [
              /* @__PURE__ */ jsxRuntime.jsx("h3", { children: "No reservations in this range" }),
              /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Change the date range or clear a filter to inspect another part of the schedule." }),
              /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: clearFilters, "data-testid": "facilities-clear-filters", children: "Reset range and filters" })
            ] }) })
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsx("aside", { className: "facilities-inspector", "aria-label": "Reservation inspector", "data-testid": "facility-inspector", children: selectedReservation ? /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "facilities-detail-sheet", "aria-labelledby": "facility-reservation-detail-title", children: [
          /* @__PURE__ */ jsxRuntime.jsx("div", { className: "facilities-detail-heading", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
            /* @__PURE__ */ jsxRuntime.jsx("span", { children: selectedReservation.seriesId ? "Recurring series" : "Reservation" }),
            /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "facility-reservation-detail-title", children: selectedReservation.title })
          ] }) }),
          /* @__PURE__ */ jsxRuntime.jsxs("dl", { className: "facilities-detail-grid", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Room" }),
              /* @__PURE__ */ jsxRuntime.jsx("dd", { children: facilities.find((item) => item.id === selectedReservation.facilityId)?.name })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Time" }),
              /* @__PURE__ */ jsxRuntime.jsxs("dd", { children: [
                displayTime(selectedReservation.start),
                "\u2013",
                displayTime(selectedReservation.end)
              ] })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Requester" }),
              /* @__PURE__ */ jsxRuntime.jsx("dd", { children: selectedReservation.requesterName })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "span-all", children: [
              /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Setup notes" }),
              /* @__PURE__ */ jsxRuntime.jsx("dd", { children: selectedReservation.notes || "No setup notes" })
            ] })
          ] }),
          /* @__PURE__ */ jsxRuntime.jsx("div", { className: "facilities-detail-actions", children: /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-danger-button", type: "button", disabled: mutationPending || (selectedReservation.seriesId ? !can("facilities.delete-series") : !canEditReservation(selectedReservation, selectedReservation.groupId ? "facilities.delete-group" : "facilities.delete-reservation")), onClick: () => selectedReservation.seriesId ? setDeleteSeriesTarget(selectedReservation) : selectedReservation.groupId ? setDeleteGroupTarget(selectedReservation) : setDeleteReservationTarget(selectedReservation), "data-testid": "facility-inspector-delete", children: selectedReservation.seriesId ? "Delete entire series" : selectedReservation.groupId ? "Delete linked group" : "Delete reservation" }) })
        ] }) : /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-inspector-empty", children: [
          /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Select a reservation" }),
          /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Choose a schedule row to inspect its room, timing, requester, and setup notes." })
        ] }) })
      ] }) : /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-rooms", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-manager-bar", "data-testid": "facility-manager-bar", children: [
          /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
            /* @__PURE__ */ jsxRuntime.jsx("strong", { children: "Space operations" }),
            /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Manage rooms and automation-created reservations." })
          ] }),
          /* @__PURE__ */ jsxRuntime.jsxs("fieldset", { disabled: mutationPending, children: [
            /* @__PURE__ */ jsxRuntime.jsx("legend", { className: "sr-only", children: "Room manager actions" }),
            /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: !can("facilities.delete-reservations"), onClick: openAutomation, "data-testid": "facility-automation-manage", children: "Manage automation reservations" }),
            /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", disabled: !can("facilities.create-facility"), onClick: () => openFacilityEditor(null), "data-testid": "facility-add-space", children: "Add Space" })
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-split-shell facilities-room-split", children: [
          /* @__PURE__ */ jsxRuntime.jsx("div", { className: "facilities-list-pane facilities-building-list", "data-testid": "facilities-rooms-list", children: groupedFacilities.map((group) => /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "facilities-building", "data-testid": `facility-building-${slug(group.building ?? "unassigned")}`, children: [
            /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("h2", { children: group.building ?? "Unassigned" }),
              /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
                group.facilities.length,
                " space",
                group.facilities.length === 1 ? "" : "s"
              ] })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsx("div", { children: group.facilities.map((facility) => {
              const upcoming = reservations.filter((reservation) => reservation.facilityId === facility.id && !reservation.automation).length;
              return /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "facilities-room-row", "aria-current": selectedRoomId === facility.id ? "true" : void 0, "data-testid": `facility-room-${facility.id}`, children: [
                /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "facilities-room-open", type: "button", onClick: () => setSelectedRoomId(facility.id), "data-testid": `facility-room-open-${facility.id}`, children: [
                  /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "facilities-room-copy", children: [
                    /* @__PURE__ */ jsxRuntime.jsx("strong", { children: facility.name }),
                    /* @__PURE__ */ jsxRuntime.jsx("small", { children: facility.description })
                  ] }),
                  /* @__PURE__ */ jsxRuntime.jsx("span", { className: "facilities-room-status", children: upcoming ? `${upcoming} upcoming` : "Available" })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: mutationPending || !canReserve, onClick: () => openReservationEditor(null, facility.id), "data-testid": `facility-room-reserve-${facility.id}`, children: "Reserve" }),
                /* @__PURE__ */ jsxRuntime.jsx(ActionMenu, { label: `Manage ${facility.name}`, testId: `facility-room-menu-${facility.id}`, children: /* @__PURE__ */ jsxRuntime.jsx("button", { className: "menu-item danger-item", role: "menuitem", type: "button", disabled: !can("facilities.delete-facility"), onClick: () => setDeleteFacilityTarget(facility), "data-testid": `facility-room-menu-delete-${facility.id}`, children: "Delete room" }) })
              ] }, facility.id);
            }) })
          ] }, group.building ?? "unassigned")) }),
          /* @__PURE__ */ jsxRuntime.jsx("aside", { className: "facilities-inspector", "aria-label": "Room inspector", children: selectedRoom ? /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "facilities-detail-sheet", "aria-labelledby": "facility-room-detail-title", children: [
            /* @__PURE__ */ jsxRuntime.jsx("div", { className: "facilities-detail-heading", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("span", { children: selectedRoom.building ?? "Unassigned" }),
              /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "facility-room-detail-title", children: selectedRoom.name }),
              /* @__PURE__ */ jsxRuntime.jsx("p", { children: selectedRoom.description })
            ] }) }),
            /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-room-preview", children: [
              /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-inspector-section-heading", children: [
                /* @__PURE__ */ jsxRuntime.jsx("h3", { children: "Upcoming reservations" }),
                /* @__PURE__ */ jsxRuntime.jsx("span", { children: reservations.filter((item) => item.facilityId === selectedRoom.id && !item.automation).length })
              ] }),
              reservations.filter((item) => item.facilityId === selectedRoom.id && !item.automation).slice(0, 5).map((reservation) => /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntime.jsx("strong", { children: reservation.title }),
                /* @__PURE__ */ jsxRuntime.jsx("span", { children: displayTime(reservation.start) })
              ] }, reservation.id))
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-detail-actions", children: [
              /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", disabled: mutationPending || !canReserve, onClick: () => openReservationEditor(null, selectedRoom.id), "data-testid": "facility-room-inspector-reserve", children: "Reserve this room" }),
              /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: mutationPending || !can("facilities.update-facility"), onClick: () => openFacilityEditor(selectedRoom), "data-testid": "facility-room-inspector-edit", children: "Edit space" })
            ] })
          ] }) : /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-inspector-empty", children: [
            /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Select a room" }),
            /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Choose a room to inspect its description and upcoming reservations." })
          ] }) })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: reservationDialogOpen, onClose: closeReservationEditor, title: editingReservation ? "Edit reservation" : "Reserve space", description: "Availability is calculated from the current room schedule.", testId: "facility-reservation-dialog", wide: true, children: /* @__PURE__ */ jsxRuntime.jsx("form", { className: "facilities-reservation-form", onSubmit: (event) => void submitReservation(event), children: /* @__PURE__ */ jsxRuntime.jsxs("fieldset", { disabled: mutationPending || !canSubmitReservation, "aria-describedby": !canSubmitReservation ? "facilities-read-only" : void 0, children: [
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-form-grid", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "field span-2", children: [
          "Title",
          /* @__PURE__ */ jsxRuntime.jsx("input", { "data-autofocus": true, value: formTitle, onChange: (event) => setFormTitle(event.target.value), "aria-invalid": Boolean(formErrors.title), "data-testid": "facility-form-title" }),
          formErrors.title && /* @__PURE__ */ jsxRuntime.jsx("span", { className: "facilities-field-error", role: "alert", "data-testid": "facility-form-title-error", children: formErrors.title })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "field span-2", children: [
          "Requester",
          /* @__PURE__ */ jsxRuntime.jsx("input", { value: formRequesterName, onChange: (event) => setFormRequesterName(event.target.value), "data-testid": "facility-form-requester" })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "field", children: [
          "Room",
          /* @__PURE__ */ jsxRuntime.jsx("select", { value: formRoomId, onChange: (event) => setFormRoomId(event.target.value), "data-testid": "facility-form-room", children: facilities.map((facility) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: facility.id, children: facility.name }, facility.id)) }),
          formErrors.room && /* @__PURE__ */ jsxRuntime.jsx("span", { className: "facilities-field-error", role: "alert", "data-testid": "facility-form-room-error", children: formErrors.room })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "field", children: [
          "Date",
          /* @__PURE__ */ jsxRuntime.jsx("input", { type: "date", value: formDate, onChange: (event) => setFormDate(event.target.value), "data-testid": "facility-form-date" })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "field", children: [
          "Start time",
          /* @__PURE__ */ jsxRuntime.jsx("input", { type: "time", value: formStart, onChange: (event) => setFormStart(event.target.value), "data-testid": "facility-form-start" })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "field", children: [
          "End time",
          /* @__PURE__ */ jsxRuntime.jsx("input", { type: "time", value: formEnd, onChange: (event) => setFormEnd(event.target.value), "data-testid": "facility-form-end" })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "field span-2", children: [
          "Setup notes",
          /* @__PURE__ */ jsxRuntime.jsx("textarea", { rows: 3, value: formNotes, onChange: (event) => setFormNotes(event.target.value), "data-testid": "facility-form-notes" })
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsx("section", { className: `facilities-availability ${formConflicts.length ? "conflict" : ""}`, "aria-live": "polite", children: /* @__PURE__ */ jsxRuntime.jsx("strong", { "data-testid": "facility-form-availability", children: availabilityText }) }),
      formErrors.slot && /* @__PURE__ */ jsxRuntime.jsx("div", { className: "facilities-form-alert", role: "alert", "data-testid": "facility-form-slot-error", children: formErrors.slot }),
      /* @__PURE__ */ jsxRuntime.jsxs("footer", { className: "dialog-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: closeReservationEditor, "data-testid": "facility-form-cancel", children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "submit", "data-testid": "facility-form-submit", children: editingReservation ? "Save changes" : "Create reservation" })
      ] })
    ] }) }) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: facilityEditorOpen, onClose: closeFacilityEditor, title: editingFacility ? "Edit space" : "Add space", description: "Facilities use only the room name, building, and description fields exposed by Rhythm.", testId: "facility-editor-dialog", children: /* @__PURE__ */ jsxRuntime.jsx("form", { onSubmit: (event) => void submitFacility(event), children: /* @__PURE__ */ jsxRuntime.jsxs("fieldset", { disabled: mutationPending || !(editingFacility ? can("facilities.update-facility") : can("facilities.create-facility")), "aria-describedby": !(editingFacility ? can("facilities.update-facility") : can("facilities.create-facility")) ? "facilities-read-only" : void 0, children: [
      /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "field", children: [
        "Room name",
        /* @__PURE__ */ jsxRuntime.jsx("input", { "data-autofocus": true, value: facilityName, onChange: (event) => {
          setFacilityName(event.target.value);
          setFacilityNameError("");
        }, "aria-invalid": Boolean(facilityNameError), "data-testid": "facility-editor-name" }),
        facilityNameError && /* @__PURE__ */ jsxRuntime.jsx("span", { className: "facilities-field-error", role: "alert", "data-testid": "facility-editor-name-error", children: facilityNameError })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "field", children: [
        "Building",
        /* @__PURE__ */ jsxRuntime.jsxs("select", { value: facilityBuilding, onChange: (event) => setFacilityBuilding(event.target.value), "data-testid": "facility-editor-building", children: [
          /* @__PURE__ */ jsxRuntime.jsx("option", { value: "", children: "Unassigned" }),
          buildings.map((building) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: building, children: building }, building)),
          /* @__PURE__ */ jsxRuntime.jsx("option", { value: "__new_building__", children: "Add a new building\u2026" })
        ] })
      ] }),
      facilityBuilding === "__new_building__" && /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "field", children: [
        "New building name",
        /* @__PURE__ */ jsxRuntime.jsx("input", { value: newBuilding, onChange: (event) => setNewBuilding(event.target.value), "data-testid": "facility-editor-new-building" })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "field", children: [
        "Description",
        /* @__PURE__ */ jsxRuntime.jsx("textarea", { rows: 4, value: facilityDescription, onChange: (event) => setFacilityDescription(event.target.value), "data-testid": "facility-editor-description" })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("footer", { className: "dialog-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: closeFacilityEditor, "data-testid": "facility-editor-cancel", children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "submit", "data-testid": "facility-editor-submit", children: editingFacility ? "Save changes" : "Add Space" })
      ] })
    ] }) }) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: automationOpen, onClose: () => setAutomationOpen(false), title: "Manage automation reservations", description: "Preview the exact cleanup scope before deleting automation-created reservations.", testId: "facility-automation-dialog", wide: true, children: /* @__PURE__ */ jsxRuntime.jsxs("fieldset", { className: "facilities-automation-form", disabled: mutationPending || !can("facilities.delete-reservations"), "aria-describedby": !can("facilities.delete-reservations") ? "facilities-read-only" : void 0, children: [
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "facilities-form-grid", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "field", children: [
          "Room",
          /* @__PURE__ */ jsxRuntime.jsxs("select", { value: automationRoom, onChange: (event) => setAutomationRoom(event.target.value), "data-testid": "facility-automation-room-filter", children: [
            /* @__PURE__ */ jsxRuntime.jsx("option", { value: "", children: "All rooms" }),
            facilities.map((facility) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: facility.id, children: facility.name }, facility.id))
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "field", children: [
          "Start after",
          /* @__PURE__ */ jsxRuntime.jsx("input", { type: "date", value: automationStart, onChange: (event) => setAutomationStart(event.target.value), "data-testid": "facility-automation-start-after" })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "field", children: [
          "End before",
          /* @__PURE__ */ jsxRuntime.jsx("input", { type: "date", value: automationEnd, onChange: (event) => setAutomationEnd(event.target.value), "data-testid": "facility-automation-end-before" })
        ] })
      ] }),
      filteredAutomation.length ? /* @__PURE__ */ jsxRuntime.jsx("section", { className: "facilities-automation-preview", "aria-live": "polite", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
        /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Reservations in scope" }),
        /* @__PURE__ */ jsxRuntime.jsx("strong", { "data-testid": "facility-automation-total", children: filteredAutomation.length })
      ] }) }) : /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "facilities-automation-zero", role: "status", "data-testid": "facility-automation-zero", children: [
        /* @__PURE__ */ jsxRuntime.jsx("h3", { children: "No automation-created reservations" }),
        /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Adjust the room or date bounds to preview a different cleanup scope." })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("footer", { className: "dialog-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => setAutomationOpen(false), "data-testid": "facility-automation-cancel", children: "Cancel" }),
        filteredAutomation.length > 0 && /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "danger-button", type: "button", disabled: mutationPending, onClick: () => void cleanupAutomation(), "data-testid": "facility-automation-delete", children: [
          "Delete ",
          filteredAutomation.length,
          " reservations"
        ] })
      ] })
    ] }) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(deleteReservationTarget), onClose: () => setDeleteReservationTarget(null), title: deleteReservationTarget ? `Delete "${deleteReservationTarget.title}"?` : "Delete reservation?", description: "This cannot be undone.", testId: "facility-reservation-delete-dialog", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => setDeleteReservationTarget(null), "data-testid": "facility-reservation-delete-cancel", children: "Cancel" }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "danger-button", type: "button", disabled: mutationPending || !canEditReservation(deleteReservationTarget, "facilities.delete-reservation"), onClick: () => void confirmDeleteReservation(), "data-testid": "facility-reservation-delete-confirm", children: "Delete reservation" })
    ] }) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(deleteSeriesTarget), onClose: () => setDeleteSeriesTarget(null), title: deleteSeriesTarget ? `Delete entire series "${deleteSeriesTarget.title}"?` : "Delete series?", description: "Every occurrence in this recurring series will be removed. This cannot be undone.", testId: "facility-series-delete-dialog", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => setDeleteSeriesTarget(null), "data-testid": "facility-series-delete-cancel", children: "Cancel" }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "danger-button", type: "button", disabled: mutationPending || !can("facilities.delete-series"), onClick: () => void confirmDeleteSeries(), "data-testid": "facility-series-delete-confirm", children: "Delete entire series" })
    ] }) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(deleteGroupTarget), onClose: () => setDeleteGroupTarget(null), title: deleteGroupTarget ? `Delete linked group "${deleteGroupTarget.title}"?` : "Delete linked group?", description: "Every linked reservation in this group will be removed. This cannot be undone.", testId: "facility-group-delete-dialog", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => setDeleteGroupTarget(null), "data-testid": "facility-group-delete-cancel", children: "Cancel" }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "danger-button", type: "button", disabled: mutationPending || !canEditReservation(deleteGroupTarget, "facilities.delete-group"), onClick: () => void confirmDeleteGroup(), "data-testid": "facility-group-delete-confirm", children: "Delete linked group" })
    ] }) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(deleteFacilityTarget), onClose: () => setDeleteFacilityTarget(null), title: deleteFacilityTarget ? `Delete "${deleteFacilityTarget.name}"?` : "Delete space?", description: "This removes the room and its reservations from this workspace. This cannot be undone.", testId: "facility-delete-dialog", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => setDeleteFacilityTarget(null), "data-testid": "facility-delete-cancel", children: "Cancel" }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "danger-button", type: "button", disabled: mutationPending || !can("facilities.delete-facility"), onClick: () => void confirmDeleteFacility(), "data-testid": "facility-delete-confirm", children: "Delete space" })
    ] }) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(operationTarget), onClose: cancelOperation, title: "Confirm facilities change", description: "Confirm this exact facilities change before it is sent to the workspace.", testId: "facility-operation-confirmation", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: mutationPending, onClick: cancelOperation, "data-testid": "facility-operation-cancel", children: "Cancel" }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", disabled: mutationPending, onClick: () => void confirmOperation(), "data-testid": "facility-operation-confirm", children: "Confirm" })
    ] }) })
  ] }) });
}
var PROVIDER_IDS = ["google-calendar", "gmail", "planning-center"];
var PROVIDER_NAMES = { "google-calendar": "Google Calendar", gmail: "Gmail", "planning-center": "Planning Center" };
function statusLabel(account) {
  if (account.status === "connected") return "Connected";
  if (account.status === "needs_reauth") return "Permission required";
  if (account.status === "error") return "Needs attention";
  return "Not connected";
}
function uniqueSignals(signals) {
  const seen = /* @__PURE__ */ new Set();
  return signals.filter((signal) => {
    if (seen.has(signal.threadId)) return false;
    seen.add(signal.threadId);
    return true;
  });
}
function StatePanel4({ state, onRetry, onConnect }) {
  if (state === "loading") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "integrations-state", role: "status", "aria-live": "polite", "data-testid": "page-state-loading", children: [
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Loading integrations" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Reading connected accounts and their provider settings." })
  ] });
  if (state === "empty") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "integrations-state", role: "status", "data-testid": "page-state-empty", children: [
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "No integrations connected" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Connect Google to begin bringing calendar and inbox context into Rhythm." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onConnect, "data-testid": "integrations-empty-connect", children: "Connect Google" })
  ] });
  if (state === "server_error") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "integrations-state danger", role: "alert", "data-testid": "page-state-server-error", children: [
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Integrations could not be loaded" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "The integration service returned a temporary error." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
  ] });
  if (state === "forbidden") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "integrations-state warning", role: "alert", "data-testid": "page-state-forbidden", children: [
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Integration access is restricted" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "An authenticated Rhythm workspace with integration access is required." })
  ] });
  return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "integrations-state warning", role: "status", "data-testid": "page-state-unavailable", children: [
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Integrations are unavailable" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Reconnect the integration service before managing connections." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
  ] });
}
function IntegrationsScreen() {
  const { integrations: gateway } = useRhythmDomainGateway();
  const host = useRhythmHost();
  const [surfaceState, setSurfaceState] = react.useState("loading");
  const [accounts, setAccounts] = react.useState([]);
  const [calendarSources, setCalendarSources] = react.useState([]);
  const [gmailSignals, setGmailSignals] = react.useState([]);
  const [selectedSection, setSelectedSection] = react.useState("google-calendar");
  const [calendarSelection, setCalendarSelection] = react.useState([]);
  const [calendarSaveStatus, setCalendarSaveStatus] = react.useState("");
  const [providerBusy, setProviderBusy] = react.useState(null);
  const [providerStatus, setProviderStatus] = react.useState({});
  const [syncingAll, setSyncingAll] = react.useState(false);
  const [syncAllStatus, setSyncAllStatus] = react.useState("");
  const [handoff, setHandoff] = react.useState(null);
  const [disconnectTarget, setDisconnectTarget] = react.useState(null);
  const [mutationPending, setMutationPending] = react.useState(false);
  const canMutate = host.currentUser.capabilities?.includes("integrations.write") ?? false;
  const mountedRef = react.useRef(true);
  const account = (id) => accounts.find((item) => item.id === id) ?? { id, name: PROVIDER_NAMES[id], monogram: "", status: "disconnected" };
  const connectedCount = accounts.filter((item) => item.status === "connected").length;
  const handleError = (error) => {
    const kind = error instanceof RhythmGatewayError ? error.kind : "server_error";
    setSurfaceState(kind === "forbidden" ? "forbidden" : kind === "not_found" ? "unavailable" : kind === "unavailable" ? "unavailable" : "server_error");
  };
  const load = async () => {
    setSurfaceState("loading");
    try {
      const [loadedAccounts, loadedCalendarSources] = await Promise.all([gateway.accounts(), gateway.calendarSources()]);
      if (!mountedRef.current) return;
      setAccounts(loadedAccounts);
      setCalendarSources(loadedCalendarSources);
      setCalendarSelection(loadedCalendarSources.filter((source) => source.selected).map((source) => source.id));
      setSurfaceState(loadedAccounts.every((item) => item.status === "disconnected") ? "empty" : "ready");
    } catch (error) {
      if (!mountedRef.current) return;
      handleError(error);
    }
  };
  react.useEffect(() => {
    mountedRef.current = true;
    void load();
    return () => {
      mountedRef.current = false;
    };
  }, [gateway]);
  react.useEffect(() => {
    if (selectedSection === "gmail" && account("gmail").status === "connected" && !gmailSignals.length) {
      void gateway.gmailSignals().then((signals) => {
        if (mountedRef.current) setGmailSignals(signals);
      }).catch(() => {
        if (mountedRef.current) setProviderStatus((current) => ({ ...current, gmail: "Gmail signals could not load. Retry syncing Gmail." }));
      });
    }
  }, [selectedSection, accounts]);
  const showsWorkspace = surfaceState === "ready";
  const requestConnect = (id, section = id) => {
    if (!canMutate) return;
    setSelectedSection(section);
    gateway.requestAuthorization(id);
    setHandoff({ provider: id, label: `Reconnecting ${PROVIDER_NAMES[id]}` });
  };
  const syncProvider = async (id) => {
    if (!canMutate) return;
    setProviderBusy(id);
    setProviderStatus((current) => ({ ...current, [id]: `Syncing ${PROVIDER_NAMES[id]}\u2026` }));
    try {
      const updated = await gateway.sync(id);
      if (!mountedRef.current) return;
      setAccounts((current) => current.map((item) => item.id === updated.id ? updated : item));
      setProviderStatus((current) => ({ ...current, [id]: `${PROVIDER_NAMES[id]} synced.` }));
    } catch (error) {
      if (!mountedRef.current) return;
      setProviderStatus((current) => ({ ...current, [id]: `${PROVIDER_NAMES[id]} could not sync. Existing data was kept.` }));
    } finally {
      if (mountedRef.current) setProviderBusy(null);
    }
  };
  const syncAll = async () => {
    if (!canMutate) return;
    setSyncingAll(true);
    setSyncAllStatus("Syncing connected services\u2026");
    const connected = accounts.filter((item) => item.status === "connected");
    const results = await Promise.all(connected.map((item) => gateway.sync(item.id).then((updated) => ({ ok: true, updated })).catch(() => ({ ok: false, id: item.id }))));
    if (!mountedRef.current) return;
    setAccounts((current) => current.map((item) => {
      const match = results.find((result) => result.ok ? result.updated.id === item.id : result.id === item.id);
      return match?.ok ? match.updated : item;
    }));
    const failed = results.filter((result) => !result.ok).length;
    setSyncAllStatus(failed ? `${connected.length - failed} of ${connected.length} services synced.` : "All connected services are up to date.");
    setSyncingAll(false);
  };
  const confirmDisconnect = async () => {
    if (!disconnectTarget) return;
    if (!canMutate) return;
    setMutationPending(true);
    try {
      const updated = await gateway.disconnect(disconnectTarget);
      if (!mountedRef.current) return;
      setAccounts((current) => current.map((item) => item.id === updated.id ? updated : item));
      setDisconnectTarget(null);
    } catch (error) {
      handleError(error);
    } finally {
      if (mountedRef.current) setMutationPending(false);
    }
  };
  const saveCalendarSelection = async () => {
    if (!canMutate) return;
    setMutationPending(true);
    setCalendarSaveStatus("Saving calendar sources\u2026");
    try {
      const saved = await gateway.saveCalendarSelection(calendarSelection);
      if (!mountedRef.current) return;
      setCalendarSources(saved);
      setCalendarSaveStatus("Calendar sources saved.");
    } catch (error) {
      if (!mountedRef.current) return;
      setCalendarSaveStatus("Calendar sources could not be saved. Your selection is still here; retry when the service is available.");
    } finally {
      if (mountedRef.current) setMutationPending(false);
    }
  };
  const requestFollowUp = (label, action) => {
    host.onRequestFollowUp?.({ screen: "integrations", label, action });
  };
  const calendar = account("google-calendar");
  const gmail = account("gmail");
  const planningCenter = account("planning-center");
  return /* @__PURE__ */ jsxRuntime.jsxs(ScreenRoot, { screenName: "Integrations", testId: "rhythm-integrations-screen", children: [
    /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "page-shell pg-integrations", "aria-busy": surfaceState === "loading", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("header", { className: "integrations-header", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
          /* @__PURE__ */ jsxRuntime.jsx("h1", { children: "Integrations" }),
          /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Bring trusted schedule and inbox context into Rhythm, then keep each provider in sync." })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsx("div", { className: "integrations-header-meta", children: /* @__PURE__ */ jsxRuntime.jsxs("span", { "data-testid": "integrations-connected-count", children: [
          /* @__PURE__ */ jsxRuntime.jsx("strong", { children: connectedCount }),
          " / 3 connected"
        ] }) }),
        showsWorkspace && /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: () => void syncAll(), disabled: syncingAll || connectedCount === 0 || mutationPending || !canMutate, "data-testid": "integrations-sync-all", children: syncingAll ? "Syncing\u2026" : "Sync all" })
      ] }),
      !canMutate && /* @__PURE__ */ jsxRuntime.jsx("p", { role: "status", "data-testid": "integrations-read-only", children: "You can inspect connections, but this account cannot change integration settings." }),
      !showsWorkspace && /* @__PURE__ */ jsxRuntime.jsx(StatePanel4, { state: surfaceState, onRetry: () => void load(), onConnect: () => requestConnect("google-calendar") }),
      showsWorkspace && /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "integrations-workspace", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "integrations-provider-list", "aria-label": "Providers", children: [
          PROVIDER_IDS.map((id) => {
            const item = account(id);
            return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "integrations-provider-row", "aria-current": selectedSection === id ? "true" : void 0, "data-testid": `integration-${id}`, children: [
              /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "integrations-provider-select", type: "button", onClick: () => setSelectedSection(id), "data-testid": `integration-select-${id}`, children: [
                /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
                  /* @__PURE__ */ jsxRuntime.jsx("strong", { children: item.name }),
                  /* @__PURE__ */ jsxRuntime.jsx("small", { children: item.identity ?? "No account identity available" }),
                  item.errorMessage && /* @__PURE__ */ jsxRuntime.jsx("em", { children: item.errorMessage })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsx("span", { className: "integrations-status", "data-testid": `integration-status-${id}`, children: statusLabel(item) })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "integrations-provider-actions", children: [
                item.status === "connected" && /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: providerBusy !== null || !canMutate, onClick: () => void syncProvider(id), "data-testid": `integration-sync-${id}`, children: providerBusy === id ? "Syncing\u2026" : "Sync" }),
                item.status === "disconnected" ? /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: !canMutate, onClick: () => requestConnect(id), "data-testid": `integration-connect-${id}`, children: "Connect" }) : /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: !canMutate, onClick: () => requestConnect(id), "data-testid": `integration-reconnect-${id}`, children: "Reconnect" }),
                item.status !== "disconnected" && /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-danger-button", type: "button", disabled: !canMutate, onClick: () => setDisconnectTarget(id), "data-testid": `integration-disconnect-${id}`, children: "Disconnect" })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsx("p", { role: "status", "aria-live": "polite", className: "integrations-provider-live", "data-testid": `integration-sync-status-${id}`, children: providerStatus[id] })
            ] }, id);
          }),
          /* @__PURE__ */ jsxRuntime.jsx("div", { className: "integrations-utility-list", children: /* @__PURE__ */ jsxRuntime.jsx("section", { "data-testid": "integration-assistant-tools", children: /* @__PURE__ */ jsxRuntime.jsxs("button", { type: "button", onClick: () => setSelectedSection("assistant-tools"), "data-testid": "integration-select-assistant-tools", children: [
            /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Assistant access" }),
            /* @__PURE__ */ jsxRuntime.jsx("small", { children: "Full Google Calendar and Gmail access for agent actions, including read + send." })
          ] }) }) })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("aside", { className: "integrations-provider-inspector", "aria-label": "Provider inspector", "data-testid": "integration-inspector", children: [
          selectedSection === "google-calendar" && /* @__PURE__ */ jsxRuntime.jsxs("section", { "aria-labelledby": "google-calendar-title", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "google-calendar-title", children: "Google Calendar" }),
              /* @__PURE__ */ jsxRuntime.jsxs("p", { children: [
                calendar.identity ?? "No account identity available",
                " \xB7 ",
                statusLabel(calendar)
              ] })
            ] }),
            calendar.status === "connected" ? /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "integrations-detail", children: [
              /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "integrations-section-heading", children: [
                /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                  /* @__PURE__ */ jsxRuntime.jsx("h3", { children: "Calendar sources" }),
                  /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Choose subscribed calendars that can create shadow-event context." })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "integrations-inline-actions", children: [
                  /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-button", type: "button", disabled: !canMutate, onClick: () => setCalendarSelection(calendarSources.map((source) => source.id)), "data-testid": "integration-calendar-select-all", children: "All" }),
                  /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-button", type: "button", disabled: !canMutate, onClick: () => setCalendarSelection([]), "data-testid": "integration-calendar-select-none", children: "None" })
                ] })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("p", { "data-testid": "integration-calendar-summary", children: [
                calendarSelection.length,
                " of ",
                calendarSources.length,
                " selected"
              ] }),
              /* @__PURE__ */ jsxRuntime.jsx("div", { className: "integrations-calendar-list", children: calendarSources.map((source) => /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
                /* @__PURE__ */ jsxRuntime.jsx("input", { type: "checkbox", disabled: !canMutate, checked: calendarSelection.includes(source.id), onChange: () => setCalendarSelection((current) => current.includes(source.id) ? current.filter((id) => id !== source.id) : [...current, source.id]), "data-testid": `integration-calendar-option-${source.id}` }),
                /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
                  /* @__PURE__ */ jsxRuntime.jsx("strong", { children: source.name }),
                  /* @__PURE__ */ jsxRuntime.jsx("small", { children: source.description })
                ] }),
                source.primary && /* @__PURE__ */ jsxRuntime.jsx("em", { children: "Primary" })
              ] }, source.id)) }),
              /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "integrations-save-row", children: [
                /* @__PURE__ */ jsxRuntime.jsx("span", { role: "status", "aria-live": "polite", "data-testid": "integration-calendar-save-status", children: calendarSaveStatus }),
                /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", disabled: mutationPending || !canMutate, onClick: () => void saveCalendarSelection(), "data-testid": "integration-calendar-save", children: "Save sources" })
              ] })
            ] }) : /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "integrations-prerequisite", "data-testid": "integration-calendar-prerequisite", children: [
              /* @__PURE__ */ jsxRuntime.jsx("strong", { children: "Calendar settings unavailable" }),
              /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Connect Google with Calendar permission to choose sources." })
            ] })
          ] }),
          selectedSection === "gmail" && /* @__PURE__ */ jsxRuntime.jsxs("section", { "aria-labelledby": "gmail-title", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "gmail-title", children: "Gmail" }),
              /* @__PURE__ */ jsxRuntime.jsxs("p", { children: [
                gmail.identity ?? "No account identity available",
                " \xB7 ",
                statusLabel(gmail)
              ] })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "integrations-detail", children: [
              /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "integrations-section-heading", children: [
                /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                  /* @__PURE__ */ jsxRuntime.jsx("h3", { children: "Recent inbox signals" }),
                  /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Up to five unique threads. This metadata connection does not grant assistant mailbox authority." })
                ] }),
                gmail.status === "connected" && /* @__PURE__ */ jsxRuntime.jsxs("strong", { "data-testid": "integration-gmail-unread-count", children: [
                  uniqueSignals(gmailSignals).filter((signal) => signal.unread).length,
                  " unread"
                ] })
              ] }),
              gmail.status === "connected" ? /* @__PURE__ */ jsxRuntime.jsx("ol", { className: "integrations-signal-list", "data-testid": "integration-gmail-signals-list", children: uniqueSignals(gmailSignals).slice(0, 5).map((signal) => /* @__PURE__ */ jsxRuntime.jsx("li", { "data-testid": `integration-gmail-signal-${signal.threadId}`, className: signal.unread ? "is-unread" : "", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntime.jsx("strong", { children: signal.subject || "(No subject)" }),
                /* @__PURE__ */ jsxRuntime.jsx("small", { children: signal.sender || "Unknown sender" }),
                signal.snippet && /* @__PURE__ */ jsxRuntime.jsx("p", { children: signal.snippet })
              ] }) }, signal.id)) }) : /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "integrations-prerequisite", "data-testid": "integration-gmail-prerequisite", children: [
                /* @__PURE__ */ jsxRuntime.jsx("strong", { children: "No inbox signals yet" }),
                /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Connect Gmail and sync once to read recent signal metadata." })
              ] })
            ] })
          ] }),
          selectedSection === "planning-center" && /* @__PURE__ */ jsxRuntime.jsxs("section", { "aria-labelledby": "planning-center-title", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "planning-center-title", children: "Planning Center" }),
              /* @__PURE__ */ jsxRuntime.jsxs("p", { children: [
                planningCenter.identity ?? "No account identity available",
                " \xB7 ",
                statusLabel(planningCenter)
              ] })
            ] }),
            planningCenter.status === "connected" ? /* @__PURE__ */ jsxRuntime.jsx("div", { className: "integrations-detail", children: /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Connected. Task-filter preferences are managed in Planning Center." }) }) : /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "integrations-prerequisite", "data-testid": "integration-planning-center-prerequisite", children: [
              /* @__PURE__ */ jsxRuntime.jsx("strong", { children: "Planning Center is locked" }),
              /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Connect Planning Center to bring plan and volunteer signals into Rhythm." })
            ] })
          ] }),
          selectedSection === "assistant-tools" && /* @__PURE__ */ jsxRuntime.jsxs("section", { "aria-labelledby": "assistant-tools-title", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "assistant-tools-title", children: "Google tools for the assistant" }),
              /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Grant the assistant full Google Calendar and Gmail access for agent actions, including read + send. This is broader than the Gmail metadata connection." })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => requestFollowUp("Enable assistant Google tools", "assistant-google-enable"), "data-testid": "integration-assistant-enable", children: "Enable" })
          ] })
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { className: "integrations-sync-all-status", role: "status", "aria-live": "polite", "data-testid": "integrations-sync-all-status", children: syncAllStatus })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs(FocusDialog, { open: Boolean(handoff), onClose: () => setHandoff(null), title: handoff?.label ?? "Authorization handoff", description: "Rhythm hands this request to the host application; it never builds or follows an authorization URL itself.", testId: "integration-handoff-dialog", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("p", { children: [
        "The host application will continue the ",
        handoff ? PROVIDER_NAMES[handoff.provider] ?? "provider" : "",
        " connection from here."
      ] }),
      /* @__PURE__ */ jsxRuntime.jsx("div", { className: "dialog-actions", children: /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: () => setHandoff(null), "data-testid": "integration-handoff-close", children: "Return to integrations" }) })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(disconnectTarget), onClose: () => setDisconnectTarget(null), title: disconnectTarget ? `Disconnect ${PROVIDER_NAMES[disconnectTarget]}?` : "Disconnect provider?", description: "This removes the connection. You can reconnect at any time.", testId: "integration-disconnect-dialog", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => setDisconnectTarget(null), "data-testid": "integration-disconnect-cancel", children: "Cancel" }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "danger-button", type: "button", disabled: mutationPending || !canMutate, onClick: () => void confirmDisconnect(), "data-testid": "integration-disconnect-confirm", children: "Disconnect" })
    ] }) })
  ] });
}
function timeLabel(timestamp) {
  const time = timestamp.slice(11, 16);
  if (!time.includes(":")) return timestamp;
  const hour = Number(time.slice(0, 2));
  return `${hour % 12 || 12}:${time.slice(3)} ${hour >= 12 ? "PM" : "AM"}`;
}
function StatePanel5({ state, onRetry, onNew }) {
  if (state === "loading") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "messages-state loading", role: "status", "aria-live": "polite", "data-testid": "page-state-loading", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Workspace messages" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Loading conversations" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Gathering thread summaries and unread state." })
  ] });
  if (state === "empty") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "messages-state", role: "status", "data-testid": "page-state-empty", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "A quiet inbox" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "No conversations" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Start a direct message or gather a group around the next handoff." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onNew, "data-testid": "messages-empty-new-thread", children: "New conversation" })
  ] });
  if (state === "server_error") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "messages-state danger", role: "alert", "data-testid": "page-state-server-error", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Retryable server error" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Messages could not be loaded" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "The message service returned a temporary error. Any open draft is preserved." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
  ] });
  if (state === "forbidden") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "messages-state warning", role: "alert", "data-testid": "page-state-forbidden", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Membership required" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Messages are restricted" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Authenticated workspace membership is required to inspect conversations." })
  ] });
  return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "messages-state warning", role: "status", "data-testid": "page-state-unavailable", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Service prerequisite" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Messages are unavailable" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Reconnect the message service before loading or changing conversations." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
  ] });
}
function ThreadActions({ thread, canWrite, onRead, onUnread, onRename, onDelete, testId }) {
  const [open, setOpen] = react.useState(false);
  const rootRef = react.useRef(null);
  const triggerRef = react.useRef(null);
  react.useEffect(() => {
    if (!open) return;
    const closeOutside = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    };
    const closeEscape = (event) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", closeOutside);
    document.addEventListener("keydown", closeEscape);
    requestAnimationFrame(() => rootRef.current?.querySelector('[role="menuitem"]')?.focus());
    return () => {
      document.removeEventListener("mousedown", closeOutside);
      document.removeEventListener("keydown", closeEscape);
    };
  }, [open]);
  const moveFocus = (event) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const items = [...event.currentTarget.querySelectorAll('[role="menuitem"]')];
    if (!items.length) return;
    event.preventDefault();
    const index = Math.max(0, items.indexOf(document.activeElement));
    const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    items[next]?.focus();
  };
  return /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "messages-thread-menu-anchor", ref: rootRef, children: [
    /* @__PURE__ */ jsxRuntime.jsx("button", { ref: triggerRef, className: "icon-button messages-thread-actions", type: "button", "aria-label": `Actions for ${thread.title}`, "aria-haspopup": "menu", "aria-expanded": open, onClick: () => setOpen((value) => !value), "data-testid": testId ?? `messages-thread-actions-${thread.id}`, children: /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "more", size: 16 }) }),
    open && /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "menu-popover messages-thread-menu", role: "menu", "aria-label": `Actions for ${thread.title}`, onKeyDown: moveFocus, children: [
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "menu-item", role: "menuitem", type: "button", disabled: !canWrite, title: !canWrite ? "This host grants inspection only." : void 0, onClick: () => {
        setOpen(false);
        thread.unreadCount > 0 ? onRead() : onUnread();
      }, "data-testid": `messages-thread-toggle-${thread.id}`, children: thread.unreadCount > 0 ? "Mark as read" : "Mark as unread" }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "menu-item", role: "menuitem", type: "button", disabled: !canWrite, title: !canWrite ? "This host grants inspection only." : void 0, onClick: () => {
        setOpen(false);
        onRename(triggerRef.current);
      }, "data-testid": `messages-thread-rename-${thread.id}`, children: "Rename thread" }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "menu-item messages-delete-action", role: "menuitem", type: "button", disabled: !canWrite, title: !canWrite ? "This host grants inspection only." : void 0, onClick: () => {
        setOpen(false);
        onDelete();
      }, "data-testid": `messages-thread-delete-${thread.id}`, children: "Delete thread" })
    ] })
  ] });
}
function MessagesScreen() {
  const { messages: gateway } = useRhythmDomainGateway();
  const host = useRhythmHost();
  const [surfaceState, setSurfaceState] = react.useState("loading");
  const [threads, setThreads] = react.useState([]);
  const [members, setMembers] = react.useState([]);
  const [selectedId, setSelectedId] = react.useState(null);
  const [search, setSearch] = react.useState("");
  const [newThreadOpen, setNewThreadOpen] = react.useState(false);
  const [threadType, setThreadType] = react.useState("direct");
  const [threadTitle, setThreadTitle] = react.useState("");
  const [selectedRecipients, setSelectedRecipients] = react.useState([]);
  const [renameTargetId, setRenameTargetId] = react.useState(null);
  const [renameTitle, setRenameTitle] = react.useState("");
  const [renameError, setRenameError] = react.useState("");
  const [deleteTargetId, setDeleteTargetId] = react.useState(null);
  const [reply, setReply] = react.useState("");
  const [replyError, setReplyError] = react.useState("");
  const [mutationPending, setMutationPending] = react.useState(false);
  const transcriptRef = react.useRef(null);
  const replyRef = react.useRef(null);
  const loadGeneration = react.useRef(0);
  const renameReturnTarget = react.useRef(null);
  const canWrite = host.currentUser.collaborationCapability === "write";
  const handleError = (error) => {
    const kind = error instanceof RhythmGatewayError ? error.kind : "server_error";
    setSurfaceState(kind === "forbidden" ? "forbidden" : kind === "not_found" ? "unavailable" : kind === "unavailable" ? "unavailable" : "server_error");
  };
  const load = async () => {
    const generation = ++loadGeneration.current;
    setSurfaceState("loading");
    try {
      const [loadedThreads, loadedMembers] = await Promise.all([gateway.list(), gateway.members()]);
      if (generation !== loadGeneration.current) return;
      setThreads(loadedThreads);
      setMembers(loadedMembers);
      setSurfaceState(loadedThreads.length ? "ready" : "empty");
    } catch (error) {
      if (generation === loadGeneration.current) handleError(error);
    }
  };
  react.useEffect(() => {
    void load();
    return () => {
      loadGeneration.current += 1;
    };
  }, [gateway]);
  const showsWorkspace = surfaceState === "ready";
  const selectedThread = threads.find((thread) => thread.id === selectedId) ?? null;
  const renameTarget = threads.find((thread) => thread.id === renameTargetId) ?? null;
  const deleteTarget = threads.find((thread) => thread.id === deleteTargetId) ?? null;
  const unreadTotal = threads.filter((thread) => thread.unreadCount > 0).length;
  const visibleThreads = react.useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return needle ? threads.filter((thread) => thread.title.toLocaleLowerCase().includes(needle)) : threads;
  }, [search, threads]);
  react.useLayoutEffect(() => {
    if (!transcriptRef.current) return;
    transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
  }, [selectedThread?.messages.length]);
  const openThread = async (id) => {
    setSelectedId(id);
    if (canWrite && threads.find((thread) => thread.id === id)?.unreadCount) {
      try {
        await gateway.markRead(id);
        setThreads((current) => current.map((thread) => thread.id === id ? { ...thread, unreadCount: 0 } : thread));
      } catch (error) {
        handleError(error);
      }
    }
  };
  const markRead = async (id) => {
    if (!canWrite) return;
    try {
      await gateway.markRead(id);
      setThreads((current) => current.map((thread) => thread.id === id ? { ...thread, unreadCount: 0 } : thread));
    } catch (error) {
      handleError(error);
    }
  };
  const markUnread = async (id) => {
    if (!canWrite) return;
    try {
      await gateway.markUnread(id);
      setThreads((current) => current.map((thread) => thread.id === id ? { ...thread, unreadCount: Math.max(1, thread.unreadCount) } : thread));
    } catch (error) {
      handleError(error);
    }
  };
  const openRenameThread = (thread, returnTarget) => {
    renameReturnTarget.current = returnTarget;
    setRenameTargetId(thread.id);
    setRenameTitle(thread.title);
    setRenameError("");
  };
  const closeRenameThread = () => {
    setRenameTargetId(null);
    setRenameTitle("");
    setRenameError("");
    requestAnimationFrame(() => renameReturnTarget.current?.focus());
  };
  const renameThread = async (event) => {
    event.preventDefault();
    if (!canWrite || !renameTarget) return;
    const title = renameTitle.trim();
    if (!title) {
      setRenameError("Enter a thread name.");
      return;
    }
    setMutationPending(true);
    try {
      const updated = await gateway.renameThread(renameTarget.id, title);
      setThreads((current) => current.map((thread) => thread.id === updated.id ? updated : thread));
      closeRenameThread();
    } catch (error) {
      handleError(error);
    } finally {
      setMutationPending(false);
    }
  };
  const openDeleteThread = (thread) => setDeleteTargetId(thread.id);
  const closeDeleteThread = () => setDeleteTargetId(null);
  const deleteThread = async () => {
    if (!canWrite || !deleteTarget) return;
    setMutationPending(true);
    try {
      await gateway.deleteThread(deleteTarget.id);
      setThreads((current) => current.filter((thread) => thread.id !== deleteTarget.id));
      if (selectedId === deleteTarget.id) {
        const visibleIndex = visibleThreads.findIndex((thread) => thread.id === deleteTarget.id);
        const adjacent = visibleIndex >= 0 ? visibleThreads[visibleIndex + 1] ?? visibleThreads[visibleIndex - 1] ?? null : threads[threads.findIndex((thread) => thread.id === deleteTarget.id) + 1] ?? threads[threads.findIndex((thread) => thread.id === deleteTarget.id) - 1] ?? null;
        setSelectedId(adjacent?.id ?? null);
        setReply("");
        setReplyError("");
      }
      closeDeleteThread();
    } catch (error) {
      handleError(error);
    } finally {
      setMutationPending(false);
    }
  };
  const openNewThread = () => {
    setNewThreadOpen(true);
    setThreadType("direct");
    setThreadTitle("");
    setSelectedRecipients([]);
  };
  const closeNewThread = () => setNewThreadOpen(false);
  const toggleRecipient = (id) => setSelectedRecipients((current) => threadType === "direct" ? [id] : current.includes(id) ? current.filter((candidate) => candidate !== id) : [...current, id]);
  const changeThreadType = (next) => {
    setThreadType(next);
    setSelectedRecipients((current) => next === "direct" ? current.slice(0, 1) : current);
  };
  const canCreate = threadType === "direct" ? selectedRecipients.length === 1 : selectedRecipients.length >= 2 && threadTitle.trim().length > 0;
  const createThread = async (event) => {
    event.preventDefault();
    if (!canWrite || !canCreate || mutationPending) return;
    setMutationPending(true);
    try {
      const created = await gateway.createThread({ participantIds: selectedRecipients, type: threadType, title: threadTitle.trim() || void 0 });
      setThreads((current) => [created, ...current]);
      setSelectedId(created.id);
      closeNewThread();
      if (surfaceState === "empty") setSurfaceState("ready");
    } catch (error) {
      handleError(error);
    } finally {
      setMutationPending(false);
    }
  };
  const sendReply = async () => {
    if (!canWrite || !selectedThread || mutationPending) return;
    const body = reply.trim();
    if (!body) {
      setReplyError("Write a message before sending.");
      replyRef.current?.focus();
      return;
    }
    setMutationPending(true);
    try {
      const message = await gateway.send(selectedThread.id, body);
      setThreads((current) => current.map((thread) => thread.id === selectedThread.id ? { ...thread, messages: [...thread.messages, message], lastMessage: body } : thread));
      setReply("");
      setReplyError("");
    } catch (error) {
      handleError(error);
    } finally {
      setMutationPending(false);
    }
  };
  return /* @__PURE__ */ jsxRuntime.jsx(ScreenRoot, { screenName: "Messages", testId: "rhythm-messages-screen", children: /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "page-shell pg-messages", "aria-busy": surfaceState === "loading", children: [
    /* @__PURE__ */ jsxRuntime.jsxs("header", { className: "messages-page-header", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "messages-heading", children: [
        /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Rhythm workspace" }),
        /* @__PURE__ */ jsxRuntime.jsx("h1", { children: "Messages" }),
        /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Move handoffs forward without losing the thread." })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "primary-button", type: "button", disabled: !showsWorkspace || !canWrite, title: !canWrite ? "You can inspect messages, but this host has not granted write permission." : void 0, onClick: openNewThread, "data-testid": "messages-new-thread", children: [
        /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "plus", size: 15 }),
        /* @__PURE__ */ jsxRuntime.jsx("span", { children: "New" })
      ] })
    ] }),
    !showsWorkspace && /* @__PURE__ */ jsxRuntime.jsx(StatePanel5, { state: surfaceState, onRetry: () => void load(), onNew: openNewThread }),
    showsWorkspace && /* @__PURE__ */ jsxRuntime.jsxs("div", { className: `messages-workspace ${selectedThread ? "has-selection" : ""}`, children: [
      /* @__PURE__ */ jsxRuntime.jsxs("aside", { className: "messages-thread-rail", "aria-label": "Conversations", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "messages-rail-summary", children: [
          /* @__PURE__ */ jsxRuntime.jsxs("strong", { "data-testid": "messages-unread-total", children: [
            unreadTotal,
            " unread ",
            unreadTotal === 1 ? "thread" : "threads"
          ] }),
          /* @__PURE__ */ jsxRuntime.jsxs("span", { "data-testid": "messages-visible-count", children: [
            visibleThreads.length,
            " ",
            visibleThreads.length === 1 ? "conversation" : "conversations"
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "search-field messages-search", children: [
          /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "search", size: 14 }),
          /* @__PURE__ */ jsxRuntime.jsx("span", { className: "sr-only", children: "Search conversations by title" }),
          /* @__PURE__ */ jsxRuntime.jsx("input", { value: search, onChange: (event) => setSearch(event.target.value), placeholder: "Search conversations", "data-testid": "messages-thread-search" })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsx("div", { className: "messages-thread-list", role: "grid", "aria-label": "Conversation list", "data-testid": "messages-thread-list", children: visibleThreads.map((thread) => /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "messages-thread-item", role: "row", children: [
          /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "messages-thread-row", role: "gridcell", tabIndex: 0, "aria-selected": selectedId === thread.id, onClick: () => void openThread(thread.id), onKeyDown: (event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              void openThread(thread.id);
            }
          }, "data-testid": `messages-thread-${thread.id}`, children: [
            /* @__PURE__ */ jsxRuntime.jsx("span", { className: "messages-thread-avatar", "aria-hidden": "true", children: thread.participants[0]?.initials ?? "R" }),
            /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "messages-thread-copy", children: [
              /* @__PURE__ */ jsxRuntime.jsx("strong", { children: thread.title }),
              /* @__PURE__ */ jsxRuntime.jsx("small", { children: thread.lastMessage })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsx("time", { dateTime: thread.updatedAt, children: timeLabel(thread.updatedAt) }),
            thread.unreadCount > 0 && /* @__PURE__ */ jsxRuntime.jsx("span", { className: "messages-row-unread", "aria-label": `${thread.unreadCount} unread message`, "data-testid": `messages-thread-unread-${thread.id}`, children: thread.unreadCount })
          ] }),
          /* @__PURE__ */ jsxRuntime.jsx("div", { role: "gridcell", children: /* @__PURE__ */ jsxRuntime.jsx(ThreadActions, { thread, canWrite, onRead: () => void markRead(thread.id), onUnread: () => void markUnread(thread.id), onRename: (target) => openRenameThread(thread, target), onDelete: () => openDeleteThread(thread) }) })
        ] }, thread.id)) }),
        visibleThreads.length === 0 && /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "messages-no-results", "data-testid": "messages-no-results", children: [
          /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "No matching conversations" }),
          /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Try a shorter title or clear the search." }),
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => setSearch(""), "data-testid": "messages-clear-search", children: "Clear search" })
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsx("section", { className: "messages-conversation", "aria-label": "Selected conversation", children: !selectedThread ? /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "messages-selection-state", "data-testid": "messages-empty-selection", children: [
        /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Select a conversation" }),
        /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Choose a thread to read its participants and transcript." })
      ] }) : /* @__PURE__ */ jsxRuntime.jsxs(jsxRuntime.Fragment, { children: [
        /* @__PURE__ */ jsxRuntime.jsxs("header", { className: "messages-conversation-header", children: [
          /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "messages-conversation-heading", children: [
            /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", "data-testid": "messages-thread-type", children: selectedThread.type === "group" ? "Group" : "Direct" }),
            /* @__PURE__ */ jsxRuntime.jsx("h2", { "data-testid": "messages-subject", children: selectedThread.title }),
            /* @__PURE__ */ jsxRuntime.jsxs("p", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("span", { "data-testid": "messages-participants", children: selectedThread.participants.map((participant) => participant.name).join(" \xB7 ") }),
              /* @__PURE__ */ jsxRuntime.jsx("span", { "aria-hidden": "true", children: " \xB7 " }),
              selectedThread.messages.length,
              " ",
              selectedThread.messages.length === 1 ? "message" : "messages"
            ] })
          ] }),
          /* @__PURE__ */ jsxRuntime.jsx(ThreadActions, { thread: selectedThread, canWrite, onRead: () => void markRead(selectedThread.id), onUnread: () => void markUnread(selectedThread.id), onRename: (target) => openRenameThread(selectedThread, target), onDelete: () => openDeleteThread(selectedThread), testId: "messages-selected-thread-actions" })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsx("div", { className: "messages-transcript", ref: transcriptRef, tabIndex: 0, "aria-label": `${selectedThread.title} transcript`, "aria-live": "polite", "data-testid": "messages-transcript", children: selectedThread.messages.length === 0 ? /* @__PURE__ */ jsxRuntime.jsx("div", { className: "messages-transcript-empty", children: /* @__PURE__ */ jsxRuntime.jsx("p", { children: "No messages yet. Start the conversation below." }) }) : selectedThread.messages.map((message) => /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "messages-message", children: [
          /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
            /* @__PURE__ */ jsxRuntime.jsx("strong", { children: message.senderName }),
            /* @__PURE__ */ jsxRuntime.jsx("time", { dateTime: message.createdAt, children: timeLabel(message.createdAt) })
          ] }),
          /* @__PURE__ */ jsxRuntime.jsx("p", { children: message.body })
        ] }, message.id)) }),
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "messages-composer", children: [
          /* @__PURE__ */ jsxRuntime.jsx("label", { htmlFor: "messages-reply-input", children: "Reply" }),
          /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
            /* @__PURE__ */ jsxRuntime.jsx(
              "textarea",
              {
                ref: replyRef,
                id: "messages-reply-input",
                rows: 2,
                value: reply,
                disabled: !canWrite,
                title: !canWrite ? "This host grants inspection only." : void 0,
                onChange: (event) => {
                  setReply(event.target.value);
                  setReplyError("");
                },
                onKeyDown: (event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void sendReply();
                  }
                },
                "aria-describedby": replyError ? "messages-reply-error" : "messages-reply-help",
                "data-testid": "messages-reply-input"
              }
            ),
            /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "primary-button messages-send", type: "button", disabled: mutationPending || !canWrite, title: !canWrite ? "This host grants inspection only." : void 0, onClick: () => void sendReply(), "data-testid": "messages-send", children: [
              /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "plus", size: 16 }),
              /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Send" })
            ] })
          ] }),
          /* @__PURE__ */ jsxRuntime.jsx("small", { id: "messages-reply-help", children: "Enter to send \xB7 Shift+Enter for a new line" }),
          replyError && /* @__PURE__ */ jsxRuntime.jsx("p", { id: "messages-reply-error", role: "alert", "data-testid": "messages-reply-error", children: replyError })
        ] })
      ] }) })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: newThreadOpen, onClose: closeNewThread, title: "New conversation", description: "Choose one person for a direct message or at least two other participants for a group.", testId: "messages-new-thread-dialog", wide: true, children: /* @__PURE__ */ jsxRuntime.jsxs("form", { className: "messages-new-thread-form", onSubmit: (event) => void createThread(event), children: [
      /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "messages-field", "data-autofocus": true, children: [
        threadType === "group" ? "Group name (required)" : "Optional title",
        /* @__PURE__ */ jsxRuntime.jsx("input", { value: threadTitle, onChange: (event) => setThreadTitle(event.target.value), "data-autofocus": true, required: threadType === "group", "data-testid": "messages-new-thread-title" })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("fieldset", { className: "messages-type-fieldset", children: [
        /* @__PURE__ */ jsxRuntime.jsx("legend", { children: "Conversation type" }),
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "messages-type-options", children: [
          /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
            /* @__PURE__ */ jsxRuntime.jsx("input", { type: "radio", name: "thread-type", value: "direct", checked: threadType === "direct", onChange: () => changeThreadType("direct"), "data-testid": "messages-thread-type-direct" }),
            "Direct"
          ] }),
          /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
            /* @__PURE__ */ jsxRuntime.jsx("input", { type: "radio", name: "thread-type", value: "group", checked: threadType === "group", onChange: () => changeThreadType("group"), "data-testid": "messages-thread-type-group" }),
            "Group"
          ] })
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("fieldset", { className: "messages-recipient-fieldset", children: [
        /* @__PURE__ */ jsxRuntime.jsx("legend", { children: threadType === "group" ? "Select participants (2 or more)" : "Select one participant" }),
        /* @__PURE__ */ jsxRuntime.jsx("div", { className: "messages-recipient-list", children: members.map((person) => /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
          /* @__PURE__ */ jsxRuntime.jsx("input", { type: "checkbox", checked: selectedRecipients.includes(person.id), onChange: () => toggleRecipient(person.id), "data-testid": `messages-recipient-${person.id}` }),
          /* @__PURE__ */ jsxRuntime.jsx("span", { className: "messages-thread-avatar", "aria-hidden": "true", children: person.initials }),
          /* @__PURE__ */ jsxRuntime.jsx("strong", { children: person.name })
        ] }, person.id)) })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: closeNewThread, "data-testid": "messages-new-thread-cancel", children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "submit", disabled: !canCreate || mutationPending, "data-testid": "messages-create-thread", children: "Create" })
      ] })
    ] }) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(renameTarget), onClose: closeRenameThread, title: "Rename thread", description: "Change how this conversation appears in Messages.", testId: "messages-rename-thread-dialog", children: /* @__PURE__ */ jsxRuntime.jsxs("form", { className: "messages-thread-edit-form", onSubmit: (event) => void renameThread(event), children: [
      /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "messages-field", children: [
        "Thread name",
        /* @__PURE__ */ jsxRuntime.jsx("input", { "data-autofocus": true, value: renameTitle, onChange: (event) => {
          setRenameTitle(event.target.value);
          setRenameError("");
        }, "aria-describedby": renameError ? "messages-rename-thread-error" : void 0, "data-testid": "messages-rename-thread-input" })
      ] }),
      renameError && /* @__PURE__ */ jsxRuntime.jsx("p", { className: "messages-form-error", id: "messages-rename-thread-error", role: "alert", "data-testid": "messages-rename-thread-error", children: renameError }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: closeRenameThread, "data-testid": "messages-rename-thread-cancel", children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "submit", disabled: mutationPending, "data-testid": "messages-rename-thread-save", children: "Save name" })
      ] })
    ] }) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(deleteTarget), onClose: closeDeleteThread, title: "Delete thread", description: deleteTarget ? `Delete "${deleteTarget.title}" and its message history? This cannot be undone.` : void 0, testId: "messages-delete-thread-dialog", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "messages-thread-delete-confirmation", children: [
      /* @__PURE__ */ jsxRuntime.jsx("p", { children: "The next conversation will stay open so you can continue working." }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: closeDeleteThread, "data-testid": "messages-delete-thread-cancel", children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "danger-button", "data-autofocus": true, type: "button", disabled: mutationPending, onClick: () => void deleteThread(), "data-testid": "messages-delete-thread-confirm", children: "Delete thread" })
      ] })
    ] }) })
  ] }) });
}

// src/components/quickActions.ts
var quickActionPresets = [
  { id: "help-finish", label: "Help me finish this" },
  { id: "draft-next-steps", label: "Draft next steps" },
  { id: "summarize", label: "Summarize" },
  { id: "follow-up-tasks", label: "Create follow-up tasks" }
];
function startOfWeek(date) {
  const day = date.getUTCDay();
  const diff = (day + 6) % 7;
  const monday = new Date(date);
  monday.setUTCDate(date.getUTCDate() - diff);
  return monday.toISOString().slice(0, 10);
}
function shiftIsoDate(iso, days) {
  const date = /* @__PURE__ */ new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
function StatePanel6({ state, onRetry, onCreate }) {
  if (state === "loading") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "planner-state", role: "status", "aria-live": "polite", "data-testid": "page-state-loading", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Weekly plan" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Loading this week\u2026" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Assembling seven day lanes, calendar context, and backlog work." }),
    /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "state-lines", "aria-hidden": "true", children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", {}),
      /* @__PURE__ */ jsxRuntime.jsx("span", {}),
      /* @__PURE__ */ jsxRuntime.jsx("span", {})
    ] })
  ] });
  if (state === "empty") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "planner-state", role: "status", "data-testid": "page-state-empty", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "A clear week" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "No work planned yet" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Add the first unscheduled task, then place it when the week takes shape." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onCreate, "data-testid": "planner-add-empty-task", children: "Add task" })
  ] });
  if (state === "server_error") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "planner-state danger", role: "alert", "data-testid": "page-state-server-error", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Retryable server error" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "This week could not load" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "The planning service returned a temporary error. Your data is unchanged." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
  ] });
  if (state === "forbidden") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "planner-state warning", role: "alert", "data-testid": "page-state-forbidden", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Workspace access required" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Planner access is restricted" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Ask a workspace administrator for planning access." })
  ] });
  return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "planner-state warning", role: "status", "data-testid": "page-state-unavailable", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Planning service prerequisite" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Planner is unavailable" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Reconnect the planning service before loading weekly work." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
  ] });
}
function TaskCard({ task, selected, canUpdate, canSchedule, onInspect, onComplete, onSelect, onDragStart }) {
  const hasSource = task.source === "task" || Boolean(task.projectStepId);
  const canMutate = canUpdate && hasSource;
  const canDrag = canSchedule && hasSource;
  return /* @__PURE__ */ jsxRuntime.jsxs("article", { className: `planner-task ${task.readonly ? "project-step" : ""} ${selected ? "selected" : ""}`, "data-status": task.status, children: [
    /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "task-main", type: "button", draggable: canDrag, "aria-label": `Inspect ${task.title}`, onDragStart: (event) => onDragStart(event, task), onClick: () => onInspect(task), "data-testid": `planner-task-${task.id}`, children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "task-source", children: task.readonly ? task.projectName ?? "Project step" : `${task.energy ?? "-"} Task` }),
      /* @__PURE__ */ jsxRuntime.jsx("strong", { children: task.title }),
      task.dueDate && task.dueDate !== task.scheduledDate && /* @__PURE__ */ jsxRuntime.jsxs("small", { children: [
        "Due ",
        task.dueDate
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "task-controls", children: [
      /* @__PURE__ */ jsxRuntime.jsx("button", { type: "button", disabled: !canMutate, title: !canUpdate ? "This host grants inspection only." : !hasSource ? "This project step is missing its source identity." : void 0, "aria-label": `Select ${task.title}`, "aria-pressed": selected, onClick: () => onSelect(task), "data-testid": `planner-task-select-${task.id}`, children: /* @__PURE__ */ jsxRuntime.jsx("span", { "aria-hidden": "true", children: selected ? "\u25C6" : "\u25C7" }) }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { type: "button", disabled: !canMutate, title: !canUpdate ? "This host grants inspection only." : !hasSource ? "This project step is missing its source identity." : void 0, "aria-label": `${task.status === "done" ? "Reopen" : "Complete"} ${task.title}`, onClick: () => onComplete(task), "data-testid": `planner-complete-${task.id}`, children: /* @__PURE__ */ jsxRuntime.jsx("span", { "aria-hidden": "true", children: task.status === "done" ? "\u21BA" : "\u2713" }) })
    ] })
  ] });
}
function CalendarEvent({ event, onInspect }) {
  return /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "calendar-event", type: "button", onClick: () => onInspect(event), "data-testid": `planner-event-${event.id}`, children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { children: event.timeLabel }),
    /* @__PURE__ */ jsxRuntime.jsx("strong", { children: event.title }),
    /* @__PURE__ */ jsxRuntime.jsx("small", { children: "Calendar \xB7 read only" })
  ] });
}
function PlannerScreen() {
  const { planner: gateway } = useRhythmDomainGateway();
  const host = useRhythmHost();
  const capabilities = host.currentUser.capabilities ?? [];
  const can = (operation) => capabilities.includes("planner.write") || capabilities.includes(operation);
  const canCreateOrCollaborate = capabilities.includes("planner.write");
  const [surfaceState, setSurfaceState] = react.useState("loading");
  const [weekStart, setWeekStart] = react.useState(() => startOfWeek(/* @__PURE__ */ new Date()));
  const [plan, setPlan] = react.useState(null);
  const [members, setMembers] = react.useState([]);
  const [filter, setFilter] = react.useState("open");
  const [selectedIds, setSelectedIds] = react.useState([]);
  const [inspector, setInspector] = react.useState(null);
  const [collaboratorPickerOpen, setCollaboratorPickerOpen] = react.useState(false);
  const [mutationPending, setMutationPending] = react.useState(false);
  const [draggedId, setDraggedId] = react.useState(null);
  const [operationTarget, setOperationTarget] = react.useState(null);
  const [operationError, setOperationError] = react.useState(null);
  const createTitleRef = react.useRef(null);
  const loadGeneration = react.useRef(0);
  const operationGeneration = react.useRef(0);
  const operationEpoch = react.useRef(0);
  const mounted = react.useRef(true);
  react.useEffect(() => () => {
    mounted.current = false;
    operationEpoch.current += 1;
  }, []);
  const handleError = (error) => {
    const kind = error instanceof RhythmGatewayError ? error.kind : "server_error";
    setSurfaceState(kind === "forbidden" ? "forbidden" : kind === "not_found" ? "unavailable" : kind === "unavailable" ? "unavailable" : "server_error");
  };
  const load = async (targetWeekStart) => {
    const generation = ++loadGeneration.current;
    setSurfaceState("loading");
    try {
      const [loadedPlan, loadedMembers] = await Promise.all([gateway.week(targetWeekStart), gateway.members()]);
      if (generation !== loadGeneration.current) return;
      setPlan(loadedPlan);
      setMembers(loadedMembers);
      const hasWork = loadedPlan.backlog.length > 0 || loadedPlan.days.some((day) => day.tasks.length > 0);
      setSurfaceState(hasWork ? "ready" : "empty");
    } catch (error) {
      if (generation === loadGeneration.current) handleError(error);
    }
  };
  react.useEffect(() => {
    void load(weekStart);
    return () => {
      loadGeneration.current += 1;
    };
  }, [gateway, weekStart]);
  const showsWorkspace = surfaceState === "ready";
  const allTasks = react.useMemo(() => plan ? [...plan.backlog, ...plan.days.flatMap((day) => day.tasks)] : [], [plan]);
  const currentTask = inspector?.kind === "task" ? allTasks.find((task) => task.id === inspector.id) ?? null : null;
  const currentEvent = inspector?.kind === "event" ? plan?.days.flatMap((day) => day.events).find((event) => event.id === inspector.id) ?? null : null;
  const operationFor = (task, kind) => task.source === "project-step" ? kind === "update" ? "planner.update-project-step" : "planner.schedule-project-step" : kind === "update" ? "planner.update-task" : "planner.schedule-task";
  const canEditCurrentTask = Boolean(currentTask && (currentTask.source === "task" || currentTask.projectStepId) && can(operationFor(currentTask, "update")));
  const canManageCurrentTaskCollaborators = Boolean(currentTask && canCreateOrCollaborate && currentTask.source === "task");
  const backlog = react.useMemo(() => (plan?.backlog ?? []).filter((task) => filter === "all" || task.status === "open"), [plan, filter]);
  const doneCount = allTasks.filter((task) => task.status === "done").length;
  const scheduledOpenCount = plan?.days.reduce((count, day) => count + day.tasks.filter((task) => task.status === "open").length, 0) ?? 0;
  const changeWeek = (next) => setWeekStart(next);
  const replaceTask = (updated) => setPlan((current) => current && { ...current, backlog: current.backlog.map((item) => item.id === updated.id ? updated : item), days: current.days.map((day) => ({ ...day, tasks: day.tasks.map((item) => item.id === updated.id ? updated : item) })) });
  const closeOperation = () => {
    operationEpoch.current += 1;
    setOperationError(null);
    setOperationTarget(null);
  };
  const requestOperation = (operation, entityId, payload, mutate) => {
    if (!can(operation) || mutationPending) return;
    operationGeneration.current += 1;
    operationEpoch.current += 1;
    setOperationError(null);
    setOperationTarget({ operation, entityId, payload, mutate, generation: `${entityId}:${operation}:${operationGeneration.current}:${Date.now()}` });
  };
  const retryOperation = () => {
    if (!operationTarget || mutationPending) return;
    operationGeneration.current += 1;
    operationEpoch.current += 1;
    setOperationError(null);
    setOperationTarget((target) => target && { ...target, generation: `${target.entityId}:${target.operation}:${operationGeneration.current}:${Date.now()}` });
  };
  const confirmOperation = async () => {
    if (!operationTarget || mutationPending) return;
    const target = operationTarget;
    const epoch = operationEpoch.current;
    setMutationPending(true);
    try {
      const confirmation = { operation: target.operation, entityId: target.entityId, payload: target.payload, generation: target.generation };
      if (host.confirmWorkspaceOperation && !await host.confirmWorkspaceOperation(confirmation)) return;
      if (!mounted.current || operationEpoch.current !== epoch || operationTarget !== target) return;
      await target.mutate();
      if (!mounted.current || operationEpoch.current !== epoch || operationTarget !== target) return;
      setOperationTarget(null);
    } catch (error) {
      const kind = error?.kind;
      if (kind === "conflict" || kind === "uncertain") setOperationError(kind);
      else handleError(error);
    } finally {
      if (mounted.current) setMutationPending(false);
    }
  };
  const changeStatus = async (task, status) => {
    if (task.source === "project-step" && !task.projectStepId) return;
    const operation = operationFor(task, "update");
    requestOperation(operation, task.source === "project-step" ? task.projectStepId : task.id, { status }, async () => {
      const updated = task.source === "project-step" ? await gateway.updateProjectStep(task.projectStepId, { status }) : await gateway.update(task.id, { status });
      replaceTask(updated);
      setSelectedIds((current) => current.filter((id) => id !== task.id));
    });
  };
  const toggleSelected = (task) => setSelectedIds((current) => current.includes(task.id) ? current.filter((id) => id !== task.id) : [...current, task.id]);
  const bulkComplete = async () => {
    const targets = allTasks.filter((task) => selectedIds.includes(task.id) && task.status === "open");
    for (const task of targets) await changeStatus(task, "done");
    setSelectedIds([]);
  };
  const onDragStart = (_event, task) => setDraggedId(task.id);
  const moveTask = async (taskId, date) => {
    const task = allTasks.find((item) => item.id === taskId);
    if (!task || task.status === "done" || task.source === "project-step" && !task.projectStepId) return;
    const operation = operationFor(task, "schedule");
    requestOperation(operation, task.source === "project-step" ? task.projectStepId : task.id, task.source === "project-step" ? { dueDate: date } : { scheduledDate: date }, async () => {
      if (task.source === "project-step") await gateway.scheduleProjectStep(task.projectStepId, { dueDate: date });
      else await gateway.scheduleTask(task.id, { scheduledDate: date });
      await load(weekStart);
    });
  };
  const dropOnDay = (event, date) => {
    event.preventDefault();
    if (draggedId) void moveTask(draggedId, date);
    setDraggedId(null);
  };
  const createTask = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    if (!canCreateOrCollaborate || !form.reportValidity()) return;
    const data = new FormData(form);
    const title = String(data.get("title") ?? "").trim();
    if (!title) {
      createTitleRef.current?.focus();
      return;
    }
    requestOperation("planner.write", "new-task", { title, notes: String(data.get("notes") ?? "").trim() || null, scheduledDate: String(data.get("scheduledDate") ?? "") || null, dueDate: String(data.get("dueDate") ?? "") || null }, async () => {
      await gateway.create({ title, notes: String(data.get("notes") ?? "").trim() || void 0, scheduledDate: String(data.get("scheduledDate") ?? "") || void 0, dueDate: String(data.get("dueDate") ?? "") || void 0 });
      await load(weekStart);
      setInspector(null);
    });
  };
  const saveTask = async (event) => {
    event.preventDefault();
    if (!currentTask || currentTask.source === "project-step" && !currentTask.projectStepId) return;
    const data = new FormData(event.currentTarget);
    const notes = String(data.get("notes") ?? "");
    const dueDate = String(data.get("dueDate") ?? "") || void 0;
    const scheduledDate = String(data.get("scheduledDate") ?? "") || void 0;
    const operation = operationFor(currentTask, "update");
    requestOperation(operation, currentTask.source === "project-step" ? currentTask.projectStepId : currentTask.id, currentTask.source === "project-step" ? { notes, dueDate: dueDate ?? null } : { notes, scheduledDate: scheduledDate ?? null, dueDate: dueDate ?? null }, async () => {
      const updated = currentTask.source === "project-step" ? await gateway.updateProjectStep(currentTask.projectStepId, { notes, dueDate }) : await gateway.update(currentTask.id, { notes, scheduledDate, dueDate });
      replaceTask(updated);
      setInspector(null);
    });
  };
  const addCollaborator = async (memberId) => {
    if (!canManageCurrentTaskCollaborators || !currentTask) return;
    requestOperation("planner.write", currentTask.id, { memberId }, async () => {
      const updated = await gateway.addCollaborator(currentTask.id, memberId);
      replaceTask(updated);
      setCollaboratorPickerOpen(false);
    });
  };
  const removeCollaborator = async (memberId) => {
    if (!canManageCurrentTaskCollaborators || !currentTask) return;
    requestOperation("planner.write", currentTask.id, { memberId }, async () => {
      const updated = await gateway.removeCollaborator(currentTask.id, memberId);
      replaceTask(updated);
    });
  };
  const launchQuickAction = (actionId, label) => {
    if (!currentTask) return;
    host.onRequestFollowUp?.({ screen: "planner", label, action: actionId, relatedId: currentTask.id });
  };
  const closeInspector = () => {
    setInspector(null);
    setCollaboratorPickerOpen(false);
  };
  return /* @__PURE__ */ jsxRuntime.jsx(ScreenRoot, { screenName: "Planner", testId: "rhythm-planner-screen", children: /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "page-shell pg-planner", "aria-busy": surfaceState === "loading", children: [
    /* @__PURE__ */ jsxRuntime.jsxs("header", { className: "planner-toolbar", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "planner-heading", children: [
        /* @__PURE__ */ jsxRuntime.jsx("h1", { children: "Planner" }),
        /* @__PURE__ */ jsxRuntime.jsxs("p", { "data-testid": "planner-week-label", children: [
          "Week of ",
          weekStart
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "planner-summary", "aria-label": "Week summary", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
          /* @__PURE__ */ jsxRuntime.jsx("strong", { children: scheduledOpenCount }),
          " scheduled open"
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
          /* @__PURE__ */ jsxRuntime.jsx("strong", { children: doneCount }),
          " completed"
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
          /* @__PURE__ */ jsxRuntime.jsx("strong", { "data-testid": "planner-backlog-count", children: backlog.length }),
          " backlog"
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "planner-header-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsx(HeaderTaskAction, { onClick: () => setInspector({ kind: "create" }), disabled: !showsWorkspace || mutationPending || !canCreateOrCollaborate, testId: "planner-header-add-task" }),
        /* @__PURE__ */ jsxRuntime.jsxs("nav", { className: "week-controls", "aria-label": "Week navigation", children: [
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", "aria-label": "Previous week", onClick: () => changeWeek(shiftIsoDate(weekStart, -7)), "data-testid": "planner-prev-week", children: "\u2190" }),
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: weekStart === startOfWeek(/* @__PURE__ */ new Date()), onClick: () => changeWeek(startOfWeek(/* @__PURE__ */ new Date())), "data-testid": "planner-today", children: "Today" }),
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", "aria-label": "Next week", onClick: () => changeWeek(shiftIsoDate(weekStart, 7)), "data-testid": "planner-next-week", children: "\u2192" })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "planner-scroll", children: [
      !showsWorkspace && /* @__PURE__ */ jsxRuntime.jsx(StatePanel6, { state: surfaceState, onRetry: () => void load(weekStart), onCreate: () => setInspector({ kind: "create" }) }),
      showsWorkspace && plan && /* @__PURE__ */ jsxRuntime.jsxs(jsxRuntime.Fragment, { children: [
        selectedIds.length > 0 && /* @__PURE__ */ jsxRuntime.jsxs("aside", { className: "selection-bar", "aria-label": "Selected tasks", children: [
          /* @__PURE__ */ jsxRuntime.jsxs("strong", { "data-testid": "planner-selection-count", children: [
            selectedIds.length,
            " selected"
          ] }),
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", disabled: !selectedIds.some((id) => {
            const task = allTasks.find((item) => item.id === id);
            return task && can(operationFor(task, "update"));
          }), title: "This host grants inspection only.", onClick: () => void bulkComplete(), "data-testid": "planner-bulk-complete", children: "Mark complete" }),
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-button", type: "button", onClick: () => setSelectedIds([]), "data-testid": "planner-clear-selection", children: "Clear" })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "planner-board", "aria-label": "Weekly plan", "data-testid": "planner-board", children: [
          /* @__PURE__ */ jsxRuntime.jsxs("aside", { className: "backlog-lane", "data-testid": "planner-backlog", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Unscheduled" }),
              /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Backlog" })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button add-control", type: "button", disabled: mutationPending || !canCreateOrCollaborate, title: !canCreateOrCollaborate ? "This host grants inspection only." : void 0, onClick: () => setInspector({ kind: "create" }), "data-testid": "planner-add-backlog-task", children: "+ Add unscheduled task" }),
            /* @__PURE__ */ jsxRuntime.jsx("div", { className: "lane-list", children: backlog.map((task) => /* @__PURE__ */ jsxRuntime.jsx(TaskCard, { task, selected: selectedIds.includes(task.id), canUpdate: can(operationFor(task, "update")), canSchedule: can(operationFor(task, "schedule")), onInspect: (item) => setInspector({ kind: "task", id: item.id }), onComplete: (item) => void changeStatus(item, item.status === "done" ? "open" : "done"), onSelect: toggleSelected, onDragStart }, task.id)) })
          ] }),
          /* @__PURE__ */ jsxRuntime.jsx("div", { className: "days-grid", children: plan.days.map((day) => {
            const dayTasks = day.tasks.filter((task) => filter === "all" || task.status === "open");
            return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "day-lane", "aria-labelledby": `planner-day-title-${day.date}`, onDragOver: (event) => event.preventDefault(), onDrop: (event) => dropOnDay(event, day.date), "data-testid": `planner-day-${day.date}`, children: [
              /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
                /* @__PURE__ */ jsxRuntime.jsx("span", { children: day.label }),
                /* @__PURE__ */ jsxRuntime.jsx("h2", { id: `planner-day-title-${day.date}`, children: day.date })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsx("div", { className: "event-list", children: day.events.map((event) => /* @__PURE__ */ jsxRuntime.jsx(CalendarEvent, { event, onInspect: (item) => setInspector({ kind: "event", id: item.id }) }, event.id)) }),
              /* @__PURE__ */ jsxRuntime.jsx("div", { className: "lane-list", children: dayTasks.map((task) => /* @__PURE__ */ jsxRuntime.jsx(TaskCard, { task, selected: selectedIds.includes(task.id), canUpdate: can(operationFor(task, "update")), canSchedule: can(operationFor(task, "schedule")), onInspect: (item) => setInspector({ kind: "task", id: item.id }), onComplete: (item) => void changeStatus(item, item.status === "done" ? "open" : "done"), onSelect: toggleSelected, onDragStart }, task.id)) }),
              /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-button add-control", type: "button", disabled: mutationPending || !canCreateOrCollaborate, title: !canCreateOrCollaborate ? "This host grants inspection only." : void 0, onClick: () => setInspector({ kind: "create", scheduledDate: day.date }), "data-testid": `planner-add-task-${day.date}`, children: "+ Add task" })
            ] }, day.date);
          }) })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "filter-control", role: "group", "aria-label": "Task visibility", children: [
          /* @__PURE__ */ jsxRuntime.jsx("button", { type: "button", "aria-pressed": filter === "open", onClick: () => setFilter("open"), "data-testid": "planner-filter-open", children: "Open" }),
          /* @__PURE__ */ jsxRuntime.jsx("button", { type: "button", "aria-pressed": filter === "all", onClick: () => setFilter("all"), "data-testid": "planner-filter-all", children: "All" })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: inspector?.kind === "create", onClose: closeInspector, title: "Add task", description: "Set the task details now. More people are available after creation.", testId: "planner-create-task-dialog", children: /* @__PURE__ */ jsxRuntime.jsx(
      TaskCreateForm,
      {
        idPrefix: "planner-create",
        onSubmit: (event) => void createTask(event),
        onCancel: closeInspector,
        members,
        titleRef: createTitleRef,
        defaultScheduledDate: inspector?.kind === "create" ? inspector.scheduledDate ?? "" : "",
        disabled: mutationPending || !canCreateOrCollaborate,
        testIds: { title: "planner-create-title", notes: "planner-create-notes", scheduledDate: "planner-create-scheduled-date", dueDate: "planner-create-due-date", collaborator: "planner-create-collaborator", cancel: "planner-create-task-cancel", submit: "planner-create-task-submit" }
      }
    ) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(currentTask), onClose: closeInspector, title: canEditCurrentTask ? "Edit task" : "Task details", description: canEditCurrentTask ? "Planner persists notes and date fields for existing tasks." : "This host grants inspection only or the source record is unavailable.", testId: "planner-inspector", children: currentTask && /* @__PURE__ */ jsxRuntime.jsxs("form", { className: "inspector-form task-editor-form", onSubmit: (event) => void saveTask(event), children: [
      /* @__PURE__ */ jsxRuntime.jsx("p", { className: "inspector-record-title", children: currentTask.title }),
      /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "task-editor-field", children: [
        "Task notes",
        /* @__PURE__ */ jsxRuntime.jsx("textarea", { name: "notes", rows: 4, disabled: !canEditCurrentTask, defaultValue: currentTask.notes, "data-autofocus": true, "data-testid": "planner-edit-notes" })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "field-pair task-editor-pair", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "task-editor-field", children: [
          "Scheduled date",
          /* @__PURE__ */ jsxRuntime.jsx("input", { name: "scheduledDate", type: "date", disabled: !canEditCurrentTask || currentTask.source === "project-step", defaultValue: currentTask.scheduledDate ?? "", "data-testid": "planner-edit-scheduled-date" })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "task-editor-field", children: [
          "Due date",
          /* @__PURE__ */ jsxRuntime.jsx("input", { name: "dueDate", type: "date", disabled: !canEditCurrentTask, defaultValue: currentTask.dueDate ?? "", "data-testid": "planner-edit-due-date" })
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "collaborators task-editor-section", "aria-labelledby": "planner-collaborators-title", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "subhead task-editor-section-head", children: [
          /* @__PURE__ */ jsxRuntime.jsx("h3", { id: "planner-collaborators-title", children: "Collaborators" }),
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: !canManageCurrentTaskCollaborators, onClick: () => setCollaboratorPickerOpen((value) => !value), "data-testid": "planner-add-collaborator", children: "Add collaborator" })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsx("div", { className: "collaborator-chips", children: currentTask.collaborators.map((member) => /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
          member.name,
          /* @__PURE__ */ jsxRuntime.jsx("button", { type: "button", disabled: !canManageCurrentTaskCollaborators, "aria-label": `Remove ${member.name}`, onClick: () => void removeCollaborator(member.id), "data-testid": `planner-remove-collaborator-${member.id}`, children: "\xD7" })
        ] }, member.id)) }),
        collaboratorPickerOpen && /* @__PURE__ */ jsxRuntime.jsx("div", { className: "collaborator-picker", role: "listbox", "aria-label": "Workspace members", children: members.filter((member) => !currentTask.collaborators.some((existing) => existing.id === member.id)).map((member) => /* @__PURE__ */ jsxRuntime.jsx("button", { type: "button", role: "option", "aria-selected": "false", onClick: () => void addCollaborator(member.id), "data-testid": `planner-collaborator-option-${member.id}`, children: member.name }, member.id)) })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "quick-actions", "aria-labelledby": "planner-quick-actions-title", children: [
        /* @__PURE__ */ jsxRuntime.jsx("h3", { id: "planner-quick-actions-title", children: "Agent handoff" }),
        quickActionPresets.map((action) => /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => launchQuickAction(action.id, action.label), "data-testid": `quick-action-${action.id}`, children: action.label }, action.id))
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("footer", { className: "task-editor-footer", children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: closeInspector, "data-testid": "planner-edit-cancel", children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "submit", disabled: mutationPending || !canEditCurrentTask, title: !canEditCurrentTask ? "This host grants inspection only." : void 0, "data-testid": "planner-save-task", children: "Save changes" })
      ] })
    ] }) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(currentEvent), onClose: closeInspector, title: "Calendar event", description: "Calendar events provide planning context and cannot be changed here.", testId: "planner-calendar-inspector", children: currentEvent && /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "readonly-details", children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Read only" }),
      /* @__PURE__ */ jsxRuntime.jsx("h3", { children: currentEvent.title }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { children: currentEvent.notes }),
      /* @__PURE__ */ jsxRuntime.jsxs("dl", { children: [
        /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
          /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Date" }),
          /* @__PURE__ */ jsxRuntime.jsx("dd", { children: currentEvent.date })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
          /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Time" }),
          /* @__PURE__ */ jsxRuntime.jsx("dd", { children: currentEvent.timeLabel })
        ] })
      ] })
    ] }) }),
    /* @__PURE__ */ jsxRuntime.jsxs(FocusDialog, { open: Boolean(operationTarget), onClose: closeOperation, title: "Confirm Planner change", description: "This exact change is sent only after you confirm it.", testId: "planner-operation-confirmation", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("p", { role: "status", children: [
        "Confirm ",
        operationTarget?.operation,
        " for this record."
      ] }),
      operationError && /* @__PURE__ */ jsxRuntime.jsxs("div", { role: "alert", "data-testid": "planner-operation-outcome", children: [
        /* @__PURE__ */ jsxRuntime.jsx("p", { children: operationError === "conflict" ? "This record changed elsewhere. Reload before retrying." : "We could not verify whether this change was applied. Reload before retrying." }),
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => void load(weekStart), "data-testid": "planner-operation-reload", children: "Reload" }),
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: retryOperation, "data-testid": "planner-operation-retry", children: "Retry" })
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: closeOperation, "data-testid": "planner-operation-cancel", children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", disabled: mutationPending, onClick: () => void confirmOperation(), "data-autofocus": true, "data-testid": "planner-operation-confirm", children: "Confirm" })
      ] })
    ] })
  ] }) });
}
function derivedStatus(instance) {
  return instance.steps.length > 0 && instance.steps.every((step) => step.status === "done") ? "Done" : "Active";
}
function StatePanel7({ state, onRetry }) {
  if (state === "loading") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "projects-state loading", role: "status", "aria-live": "polite", "data-testid": "page-state-loading", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Project ledger" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Loading projects" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Gathering templates, people, milestones, and active work." }),
    /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "state-lines", "aria-hidden": "true", children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", {}),
      /* @__PURE__ */ jsxRuntime.jsx("span", {}),
      /* @__PURE__ */ jsxRuntime.jsx("span", {})
    ] })
  ] });
  if (state === "empty") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "projects-state", role: "status", "data-testid": "page-state-empty", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "A clear ledger" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "No projects yet" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Choose a template below to start the first project from a tested sequence." })
  ] });
  if (state === "server_error") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "projects-state danger", role: "alert", "data-testid": "page-state-server-error", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Retryable server error" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Could not load projects" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "The project service returned an error without discarding the current context." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
  ] });
  if (state === "forbidden") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "projects-state warning", role: "alert", "data-testid": "page-state-forbidden", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Workspace permission required" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Projects access is restricted" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Ask a workspace administrator for project access." })
  ] });
  return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "projects-state warning", role: "status", "data-testid": "page-state-unavailable", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Service prerequisite" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Projects are unavailable" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Reconnect the project service before loading or changing projects." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
  ] });
}
function Field({ label, children }) {
  return /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "project-field", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { children: label }),
    children
  ] });
}
function ProjectsScreen() {
  const { projects: gateway } = useRhythmDomainGateway();
  const host = useRhythmHost();
  const capabilities = host.currentUser.capabilities ?? [];
  const can = (operation) => capabilities.includes("projects.write") || capabilities.includes(operation);
  const isOwner = (ownerId) => Boolean(host.currentUser.id && host.currentUser.id === ownerId);
  const [surfaceState, setSurfaceState] = react.useState("loading");
  const [templates, setTemplates] = react.useState([]);
  const [instances, setInstances] = react.useState([]);
  const [members, setMembers] = react.useState([]);
  const [showCompleted, setShowCompleted] = react.useState(false);
  const [selectedTemplateId, setSelectedTemplateId] = react.useState(null);
  const [selectedInstanceId, setSelectedInstanceId] = react.useState(null);
  const [startOpen, setStartOpen] = react.useState(false);
  const [anchorDate, setAnchorDate] = react.useState("");
  const [instanceName, setInstanceName] = react.useState("");
  const [milestoneOpen, setMilestoneOpen] = react.useState(false);
  const [instanceDelete, setInstanceDelete] = react.useState(null);
  const [inspector, setInspector] = react.useState(null);
  const [inspectorDraft, setInspectorDraft] = react.useState(null);
  const [mutationPending, setMutationPending] = react.useState(false);
  const [templateEditor, setTemplateEditor] = react.useState(null);
  const [templateStepEditor, setTemplateStepEditor] = react.useState(null);
  const [operationTarget, setOperationTarget] = react.useState(null);
  const [operationError, setOperationError] = react.useState(null);
  const loadGeneration = react.useRef(0);
  const operationGeneration = react.useRef(0);
  const operationEpoch = react.useRef(0);
  const mounted = react.useRef(true);
  const handleError = (error) => {
    const kind = error instanceof RhythmGatewayError ? error.kind : "server_error";
    setSurfaceState(kind === "forbidden" ? "forbidden" : kind === "not_found" ? "unavailable" : kind === "unavailable" ? "unavailable" : "server_error");
  };
  const load = async () => {
    const generation = ++loadGeneration.current;
    setSurfaceState("loading");
    try {
      const [loadedTemplates, loadedInstances, loadedMembers] = await Promise.all([gateway.templates(), gateway.list(), gateway.members()]);
      if (generation !== loadGeneration.current) return;
      setTemplates(loadedTemplates);
      setInstances(loadedInstances);
      setMembers(loadedMembers);
      setSurfaceState(loadedTemplates.length || loadedInstances.length ? "ready" : "empty");
    } catch (error) {
      if (generation === loadGeneration.current) handleError(error);
    }
  };
  react.useEffect(() => {
    void load();
    return () => {
      loadGeneration.current += 1;
    };
  }, [gateway]);
  react.useEffect(() => () => {
    mounted.current = false;
    operationEpoch.current += 1;
  }, []);
  const showsWorkspace = surfaceState === "ready";
  const visibleInstances = react.useMemo(() => instances.filter((instance) => showCompleted || derivedStatus(instance) !== "Done"), [instances, showCompleted]);
  const selectedInstance = visibleInstances.find((instance) => instance.id === selectedInstanceId) ?? visibleInstances[0] ?? null;
  const selectedTemplate = templates.find((template) => template.id === selectedTemplateId) ?? templates[0] ?? null;
  const inspectorInstance = inspector ? instances.find((instance) => instance.id === inspector.instanceId) ?? null : null;
  const inspectorStep = inspector && inspectorInstance ? inspectorInstance.steps.find((step) => step.id === inspector.stepId) ?? null : null;
  const applyInstance = (updated) => setInstances((current) => current.map((instance) => instance.id === updated.id ? updated : instance));
  const applyStep = (instanceId, step) => setInstances((current) => current.map((instance) => instance.id === instanceId ? { ...instance, steps: instance.steps.map((item) => item.id === step.id ? step : item) } : instance));
  const closeOperation = () => {
    operationEpoch.current += 1;
    setOperationError(null);
    setOperationTarget(null);
  };
  const requestOperation = (operation, entityId, payload, mutate) => {
    if (!can(operation) || mutationPending) return;
    operationGeneration.current += 1;
    operationEpoch.current += 1;
    setOperationError(null);
    setOperationTarget({ operation, entityId, payload, mutate, generation: `${entityId}:${operation}:${operationGeneration.current}:${Date.now()}` });
  };
  const retryOperation = () => {
    if (!operationTarget || mutationPending) return;
    operationGeneration.current += 1;
    operationEpoch.current += 1;
    setOperationError(null);
    setOperationTarget((target) => target && { ...target, generation: `${target.entityId}:${target.operation}:${operationGeneration.current}:${Date.now()}` });
  };
  const confirmOperation = async () => {
    if (!operationTarget || mutationPending) return;
    const target = operationTarget;
    const epoch = operationEpoch.current;
    setMutationPending(true);
    try {
      const confirmation = { operation: target.operation, entityId: target.entityId, payload: target.payload, generation: target.generation };
      if (host.confirmWorkspaceOperation && !await host.confirmWorkspaceOperation(confirmation)) return;
      if (!mounted.current || operationEpoch.current !== epoch || operationTarget !== target) return;
      await target.mutate();
      if (!mounted.current || operationEpoch.current !== epoch || operationTarget !== target) return;
      setOperationTarget(null);
    } catch (error) {
      const kind = error?.kind;
      if (kind === "conflict" || kind === "uncertain") setOperationError(kind);
      else handleError(error);
    } finally {
      if (mounted.current) setMutationPending(false);
    }
  };
  const toggleComplete = async (instance, step) => {
    requestOperation("projects.update-step", step.id, { instanceId: instance.id, status: step.status === "done" ? "open" : "done" }, async () => {
      const updated = await gateway.updateStep(instance.id, step.id, { instanceId: instance.id, status: step.status === "done" ? "open" : "done" });
      applyStep(instance.id, updated);
    });
  };
  const assignMilestone = async (instance, step, milestoneId) => {
    requestOperation("projects.update-step", step.id, { instanceId: instance.id, milestoneId: milestoneId || null }, async () => {
      const updated = await gateway.updateStep(instance.id, step.id, { instanceId: instance.id, milestoneId: milestoneId || null });
      applyStep(instance.id, updated);
    });
  };
  const openInspector = (instance, step) => {
    setInspector({ instanceId: instance.id, stepId: step.id });
    setInspectorDraft({ title: step.title, notes: step.notes, scheduledDate: step.scheduledDate ?? "", dueDate: step.dueDate ?? "", assigneeId: step.assigneeId ?? "" });
  };
  const closeInspector = () => {
    setInspector(null);
    setInspectorDraft(null);
  };
  const saveInspector = async (event) => {
    event.preventDefault();
    if (!inspector || !inspectorDraft || !inspectorDraft.title.trim()) return;
    const input = { ...inspectorDraft, title: inspectorDraft.title.trim() };
    requestOperation("projects.update-step", inspector.stepId, { instanceId: inspector.instanceId, title: input.title.slice(0, 200), notes: input.notes.slice(0, 2e3), scheduledDate: input.scheduledDate || null, dueDate: input.dueDate || null, assigneeId: input.assigneeId || null }, async () => {
      const updated = await gateway.updateStep(inspector.instanceId, inspector.stepId, { ...input, instanceId: inspector.instanceId });
      applyStep(inspector.instanceId, updated);
      closeInspector();
    });
  };
  const addMilestone = async (event) => {
    event.preventDefault();
    if (!selectedInstance || !isOwner(selectedInstance.ownerId)) return;
    const title = String(new FormData(event.currentTarget).get("title") ?? "").trim();
    if (!title) return;
    requestOperation("projects.create-milestone", selectedInstance.id, { title: title.slice(0, 200) }, async () => {
      const milestone = await gateway.addMilestone(selectedInstance.id, { title });
      applyInstance({ ...selectedInstance, milestones: [...selectedInstance.milestones, milestone] });
      setMilestoneOpen(false);
    });
  };
  const confirmDelete = async () => {
    if (!instanceDelete || !isOwner(instanceDelete.ownerId)) return;
    const instance = instanceDelete;
    setInstanceDelete(null);
    requestOperation("projects.delete-instance", instance.id, {}, async () => {
      await gateway.delete(instance.id);
      setInstances((current) => current.filter((item) => item.id !== instance.id));
    });
  };
  const startProject = async (event) => {
    event.preventDefault();
    if (!selectedTemplate || !anchorDate) return;
    const normalizedName = instanceName.trim().slice(0, 200);
    const input = { anchorDate };
    if (normalizedName) input.name = normalizedName;
    requestOperation("projects.create-instance", selectedTemplate.id, input, async () => {
      const created = await gateway.generate(selectedTemplate.id, input);
      setInstances((current) => [...current, created]);
      setSelectedInstanceId(created.id);
      setStartOpen(false);
      setAnchorDate("");
      setInstanceName("");
      if (surfaceState === "empty") setSurfaceState("ready");
    });
  };
  const saveTemplate = async (event) => {
    event.preventDefault();
    if (!templateEditor) return;
    const data = new FormData(event.currentTarget);
    const input = { name: String(data.get("name") ?? "").trim(), description: String(data.get("description") ?? "").trim(), anchorType: String(data.get("anchorType") ?? "").trim() };
    if (!input.name || !input.anchorType) return;
    const editor = templateEditor;
    requestOperation(editor === "new" ? "projects.create-template" : "projects.update-template", editor === "new" ? "new-template" : editor.id, { name: input.name.slice(0, 200), description: input.description.slice(0, 2e3), anchorType: input.anchorType.slice(0, 200) }, async () => {
      const saved = editor === "new" ? await gateway.createTemplate(input) : await gateway.updateTemplate(editor.id, input);
      setTemplates((current) => templateEditor === "new" ? current.some((template) => template.id === saved.id) ? current : [...current, saved] : current.map((template) => template.id === saved.id ? saved : template));
      setSelectedTemplateId(saved.id);
      setTemplateEditor(null);
    });
  };
  const deleteTemplate = async (template) => {
    requestOperation("projects.delete-template", template.id, {}, async () => {
      await gateway.deleteTemplate(template.id);
      setTemplates((current) => current.filter((item) => item.id !== template.id));
      setSelectedTemplateId(null);
    });
  };
  const saveTemplateStep = async (event) => {
    event.preventDefault();
    if (!templateStepEditor) return;
    const data = new FormData(event.currentTarget);
    const input = {
      title: String(data.get("title") ?? "").trim(),
      offsetDays: Number(data.get("offsetDays") ?? 0),
      offsetDescription: String(data.get("offsetDescription") ?? "").trim(),
      assigneeId: String(data.get("assigneeId") ?? "") || void 0
    };
    if (!input.title || !Number.isFinite(input.offsetDays) || !input.offsetDescription) return;
    const editor = templateStepEditor;
    requestOperation(editor.step ? "projects.update-template-step" : "projects.create-step", editor.step?.id ?? editor.templateId, { templateId: editor.templateId, title: input.title.slice(0, 200), offsetDays: input.offsetDays, offsetDescription: input.offsetDescription.slice(0, 200), assigneeId: input.assigneeId ?? null }, async () => {
      const saved = editor.step ? await gateway.updateTemplateStep(editor.templateId, editor.step.id, { ...input, templateId: editor.templateId }) : await gateway.addTemplateStep(editor.templateId, { ...input, templateId: editor.templateId });
      setTemplates((current) => current.map((template) => template.id !== templateStepEditor.templateId ? template : {
        ...template,
        steps: templateStepEditor.step ? template.steps.map((step) => step.id === saved.id ? saved : step) : template.steps.some((step) => step.id === saved.id) ? template.steps : [...template.steps, saved]
      }));
      setTemplateEditor((current) => current === "new" || !current || current.id !== templateStepEditor.templateId ? current : {
        ...current,
        steps: templateStepEditor.step ? current.steps.map((step) => step.id === saved.id ? saved : step) : current.steps.some((step) => step.id === saved.id) ? current.steps : [...current.steps, saved]
      });
      setTemplateStepEditor(null);
    });
  };
  const deleteTemplateStep = async (templateId, stepId) => {
    requestOperation("projects.delete-step", stepId, { templateId }, async () => {
      await gateway.deleteTemplateStep(templateId, stepId);
      const remove = (template) => ({ ...template, steps: template.steps.filter((step) => step.id !== stepId) });
      setTemplates((current) => current.map((template) => template.id === templateId ? remove(template) : template));
      setTemplateEditor((current) => current === "new" || !current || current.id !== templateId ? current : remove(current));
    });
  };
  const renderStepRow = (instance, step) => /* @__PURE__ */ jsxRuntime.jsxs("article", { className: "instance-step", "data-status": step.status, "data-testid": `project-instance-step-${step.id}`, children: [
    /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "step-check", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "sr-only", children: [
        step.status === "done" ? "Reopen" : "Complete",
        " ",
        step.title
      ] }),
      /* @__PURE__ */ jsxRuntime.jsx("input", { type: "checkbox", checked: step.status === "done", disabled: mutationPending || !can("projects.update-step"), title: !can("projects.update-step") ? "This host grants inspection only." : void 0, onChange: () => void toggleComplete(instance, step), "data-testid": `project-step-complete-${step.id}` }),
      /* @__PURE__ */ jsxRuntime.jsx("span", { "aria-hidden": "true" })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "step-copy", children: [
      /* @__PURE__ */ jsxRuntime.jsx("strong", { children: step.title }),
      /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
        step.scheduledDate ?? "No date",
        " \xB7 ",
        members.find((person) => person.id === step.assigneeId)?.name ?? "Unassigned"
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "milestone-select", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "sr-only", children: [
        "Milestone for ",
        step.title
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("select", { value: step.milestoneId ?? "", disabled: mutationPending || !can("projects.update-step"), title: !can("projects.update-step") ? "This host grants inspection only." : void 0, onChange: (event) => void assignMilestone(instance, step, event.target.value), "data-testid": `project-step-milestone-${step.id}`, children: [
        /* @__PURE__ */ jsxRuntime.jsx("option", { value: "", children: "Ungrouped" }),
        instance.milestones.map((milestone) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: milestone.id, children: milestone.title }, milestone.id))
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "icon-button", type: "button", "aria-label": `Inspect ${step.title}`, onClick: () => openInspector(instance, step), "data-testid": `project-step-inspect-${step.id}`, children: "\u2197" })
  ] }, step.id);
  return /* @__PURE__ */ jsxRuntime.jsx(ScreenRoot, { screenName: "Projects", testId: "rhythm-projects-screen", children: /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "page-shell pg-projects", "aria-busy": surfaceState === "loading", children: [
    /* @__PURE__ */ jsxRuntime.jsxs("header", { className: "projects-header", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "projects-heading", children: [
        /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Ministry work" }),
        /* @__PURE__ */ jsxRuntime.jsx("h1", { children: "Projects" }),
        /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Start repeatable work from a template and manage active project steps." })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("span", { "data-testid": "projects-visible-count", children: [
        visibleInstances.length,
        " ",
        visibleInstances.length === 1 ? "project" : "projects"
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "projects-scroll", children: [
      !showsWorkspace && /* @__PURE__ */ jsxRuntime.jsx(StatePanel7, { state: surfaceState, onRetry: () => void load() }),
      showsWorkspace && /* @__PURE__ */ jsxRuntime.jsxs(jsxRuntime.Fragment, { children: [
        /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "templates-rail", "aria-labelledby": "project-templates-title", children: [
          /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
            /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "project-templates-title", children: "Templates" }),
            /* @__PURE__ */ jsxRuntime.jsx("span", { children: templates.length }),
            /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: !can("projects.create-template"), title: !can("projects.create-template") ? "This host grants inspection only." : void 0, onClick: () => setTemplateEditor("new"), "data-testid": "project-template-new", children: "New template" })
          ] }),
          /* @__PURE__ */ jsxRuntime.jsx("div", { className: "template-list", role: "grid", "aria-label": "Project templates", "data-testid": "project-templates-list", children: templates.map((template) => /* @__PURE__ */ jsxRuntime.jsx("div", { className: "template-row", role: "row", "aria-selected": template.id === selectedTemplate?.id ? "true" : "false", "data-testid": `project-template-${template.id}`, children: /* @__PURE__ */ jsxRuntime.jsxs("div", { role: "gridcell", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "template-select", type: "button", onClick: () => {
              closeOperation();
              setSelectedTemplateId(template.id);
            }, "data-testid": `project-template-select-${template.id}`, children: [
              /* @__PURE__ */ jsxRuntime.jsx("strong", { children: template.name }),
              /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
                template.steps.length,
                " steps \xB7 ",
                template.anchorType
              ] })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-button", type: "button", disabled: !(can("projects.update-template") || can("projects.create-step") || can("projects.update-step") || can("projects.delete-step")), onClick: () => setTemplateEditor(template), "data-testid": `project-template-edit-${template.id}`, children: "Edit" }),
            /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-danger-button", type: "button", disabled: !can("projects.delete-template"), onClick: () => void deleteTemplate(template), "data-testid": `project-template-delete-${template.id}`, children: "Delete" })
          ] }) }, template.id)) }),
          selectedTemplate && /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", disabled: !can("projects.create-instance"), title: !can("projects.create-instance") ? "This host grants inspection only." : void 0, onClick: () => setStartOpen(true), "data-testid": "project-start", children: "Start Project" })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "active-projects", "aria-labelledby": "active-projects-title", children: [
          /* @__PURE__ */ jsxRuntime.jsxs("header", { className: "active-toolbar", children: [
            /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "active-projects-title", children: "Active projects" }),
            /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", "aria-pressed": showCompleted, onClick: () => setShowCompleted((value) => !value), "data-testid": "projects-show-completed", children: showCompleted ? "Hide completed" : "Show completed" })
          ] }),
          /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "project-board", children: [
            /* @__PURE__ */ jsxRuntime.jsx("section", { className: "project-list-pane", "aria-label": "Active project list", children: /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "instance-list", children: [
              visibleInstances.map((instance) => /* @__PURE__ */ jsxRuntime.jsx("article", { className: `instance-row${selectedInstance?.id === instance.id ? " selected" : ""}`, "data-testid": `project-instance-${instance.id}`, children: /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "instance-expand", type: "button", "aria-pressed": selectedInstance?.id === instance.id, onClick: () => {
                closeOperation();
                setSelectedInstanceId(instance.id);
              }, "data-testid": `project-instance-expand-${instance.id}`, children: [
                /* @__PURE__ */ jsxRuntime.jsx("span", { className: "instance-date", children: instance.anchorDate }),
                /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "instance-row-copy", children: [
                  /* @__PURE__ */ jsxRuntime.jsx("strong", { children: instance.name }),
                  /* @__PURE__ */ jsxRuntime.jsxs("small", { children: [
                    instance.steps.filter((step) => step.status === "done").length,
                    "/",
                    instance.steps.length,
                    " steps"
                  ] })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsx("span", { className: "status-badge", "data-testid": `project-instance-status-${instance.id}`, children: derivedStatus(instance) })
              ] }) }, instance.id)),
              visibleInstances.length === 0 && /* @__PURE__ */ jsxRuntime.jsx("p", { className: "inline-empty", "data-testid": "projects-no-active", children: "No active projects yet. Start one from a template above." })
            ] }) }),
            selectedInstance ? /* @__PURE__ */ jsxRuntime.jsxs("aside", { className: "project-inspector", "aria-label": "Selected project", "data-testid": "project-inspector", children: [
              /* @__PURE__ */ jsxRuntime.jsxs("header", { className: "project-inspector-header", children: [
                /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                  /* @__PURE__ */ jsxRuntime.jsx("h2", { children: selectedInstance.name }),
                  /* @__PURE__ */ jsxRuntime.jsxs("p", { children: [
                    selectedInstance.anchorDate,
                    " \xB7 ",
                    derivedStatus(selectedInstance)
                  ] })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsx("button", { className: "danger-button", type: "button", disabled: mutationPending || !can("projects.delete-instance") || !isOwner(selectedInstance.ownerId), title: !isOwner(selectedInstance.ownerId) ? "Only the project owner can delete or manage collaborators." : !can("projects.delete-instance") ? "This host grants inspection only." : void 0, onClick: () => setInstanceDelete(selectedInstance), "data-testid": `project-instance-delete-${selectedInstance.id}`, children: "Delete" })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "people-strip", "aria-labelledby": `people-${selectedInstance.id}`, children: [
                /* @__PURE__ */ jsxRuntime.jsx("h3", { id: `people-${selectedInstance.id}`, children: "Collaborators" }),
                /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "people-list", children: [
                  selectedInstance.collaborators.map((person) => /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "person-chip", "data-testid": `project-collaborator-${person.id}`, children: [
                    /* @__PURE__ */ jsxRuntime.jsx("i", { "aria-hidden": "true", children: person.initials }),
                    /* @__PURE__ */ jsxRuntime.jsx("strong", { children: person.name }),
                    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "icon-button", type: "button", disabled: true, "aria-label": `Remove ${person.name}`, title: "Collaborator management is not available in this workspace.", "data-testid": `project-collaborator-remove-${person.id}`, children: "\xD7" })
                  ] }, person.id)),
                  /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: true, title: "Collaborator management is not available in this workspace.", "data-testid": "project-collaborator-add", children: "Add person" })
                ] })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "timeline-toolbar", children: [
                /* @__PURE__ */ jsxRuntime.jsx("h3", { children: "Milestones and steps" }),
                /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: mutationPending || !can("projects.create-milestone") || !isOwner(selectedInstance.ownerId), onClick: () => setMilestoneOpen(true), "data-testid": "project-milestone-add", children: "Add milestone" })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "milestone-list", children: [
                selectedInstance.milestones.map((milestone) => /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "milestone-group", "data-testid": `project-milestone-${milestone.id}`, children: [
                  /* @__PURE__ */ jsxRuntime.jsx("header", { children: /* @__PURE__ */ jsxRuntime.jsx("h4", { children: milestone.title }) }),
                  selectedInstance.steps.filter((step) => step.milestoneId === milestone.id).map((step) => renderStepRow(selectedInstance, step))
                ] }, milestone.id)),
                /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "milestone-group ungrouped", "data-testid": "project-milestone-ungrouped", children: [
                  /* @__PURE__ */ jsxRuntime.jsx("header", { children: /* @__PURE__ */ jsxRuntime.jsx("h4", { children: "Ungrouped" }) }),
                  selectedInstance.steps.filter((step) => !step.milestoneId).map((step) => renderStepRow(selectedInstance, step))
                ] })
              ] })
            ] }) : /* @__PURE__ */ jsxRuntime.jsxs("aside", { className: "project-inspector empty", "aria-label": "Selected project", "data-testid": "project-inspector", children: [
              /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Select a project" }),
              /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Project details, people, milestones, and steps appear here." })
            ] })
          ] })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: startOpen, onClose: () => setStartOpen(false), title: "Start Project", description: selectedTemplate ? `Generate from ${selectedTemplate.name}.` : void 0, testId: "project-start-dialog", wide: true, children: /* @__PURE__ */ jsxRuntime.jsxs("form", { className: "project-dialog-form", onSubmit: startProject, children: [
      /* @__PURE__ */ jsxRuntime.jsx(Field, { label: "Project name (optional)", children: /* @__PURE__ */ jsxRuntime.jsx("input", { "data-autofocus": true, value: instanceName, onChange: (event) => setInstanceName(event.target.value), "data-testid": "project-instance-name" }) }),
      /* @__PURE__ */ jsxRuntime.jsx(Field, { label: "Anchor date", children: /* @__PURE__ */ jsxRuntime.jsx("input", { type: "date", value: anchorDate, onChange: (event) => setAnchorDate(event.target.value), "data-testid": "project-anchor-date" }) }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => setStartOpen(false), "data-testid": "project-start-cancel", children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "submit", disabled: !anchorDate || mutationPending, "data-testid": "project-start-submit", children: "Start Project" })
      ] })
    ] }) }),
    /* @__PURE__ */ jsxRuntime.jsxs(FocusDialog, { open: Boolean(templateEditor), onClose: () => setTemplateEditor(null), title: templateEditor === "new" ? "New template" : "Edit template", description: "Templates stay reusable; project instances are unchanged.", testId: "project-template-dialog", children: [
      templateEditor && /* @__PURE__ */ jsxRuntime.jsxs("form", { className: "project-dialog-form", onSubmit: saveTemplate, children: [
        /* @__PURE__ */ jsxRuntime.jsx(Field, { label: "Template name", children: /* @__PURE__ */ jsxRuntime.jsx("input", { name: "name", "data-autofocus": true, defaultValue: templateEditor === "new" ? "" : templateEditor.name, "data-testid": "project-template-name" }) }),
        /* @__PURE__ */ jsxRuntime.jsx(Field, { label: "Description", children: /* @__PURE__ */ jsxRuntime.jsx("textarea", { name: "description", defaultValue: templateEditor === "new" ? "" : templateEditor.description, "data-testid": "project-template-description" }) }),
        /* @__PURE__ */ jsxRuntime.jsx(Field, { label: "Anchor type", children: /* @__PURE__ */ jsxRuntime.jsx("input", { name: "anchorType", defaultValue: templateEditor === "new" ? "Service date" : templateEditor.anchorType, "data-testid": "project-template-anchor-type" }) }),
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => setTemplateEditor(null), children: "Cancel" }),
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "submit", disabled: mutationPending || !can(templateEditor === "new" ? "projects.create-template" : "projects.update-template"), "data-testid": "project-template-save", children: "Save template" })
        ] })
      ] }),
      templateEditor !== "new" && templateEditor && /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "template-step-editor", "aria-labelledby": "project-template-steps-title", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
          /* @__PURE__ */ jsxRuntime.jsx("h3", { id: "project-template-steps-title", children: "Template steps" }),
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: !can("projects.create-step"), title: !can("projects.create-step") ? "This host grants inspection only." : void 0, onClick: () => setTemplateStepEditor({ templateId: templateEditor.id }), "data-testid": "project-template-step-add", children: "Add step" })
        ] }),
        templateEditor.steps.map((step) => /* @__PURE__ */ jsxRuntime.jsxs("div", { "data-testid": `project-template-step-${step.id}`, children: [
          /* @__PURE__ */ jsxRuntime.jsx("strong", { children: step.title }),
          /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
            step.offsetDescription,
            " \xB7 ",
            members.find((person) => person.id === step.assigneeId)?.name ?? "Unassigned"
          ] }),
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-button", type: "button", disabled: !can("projects.update-template-step"), onClick: () => setTemplateStepEditor({ templateId: templateEditor.id, step }), "data-testid": `project-template-step-edit-${step.id}`, children: "Edit" }),
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-danger-button", type: "button", disabled: !can("projects.delete-step"), onClick: () => void deleteTemplateStep(templateEditor.id, step.id), "data-testid": `project-template-step-delete-${step.id}`, children: "Delete" })
        ] }, step.id))
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(templateStepEditor), onClose: () => setTemplateStepEditor(null), title: templateStepEditor?.step ? "Edit template step" : "Add template step", description: "Offsets are relative to the project anchor date.", testId: "project-template-step-dialog", children: templateStepEditor && /* @__PURE__ */ jsxRuntime.jsxs("form", { className: "project-dialog-form", onSubmit: saveTemplateStep, children: [
      /* @__PURE__ */ jsxRuntime.jsx(Field, { label: "Step title", children: /* @__PURE__ */ jsxRuntime.jsx("input", { name: "title", "data-autofocus": true, defaultValue: templateStepEditor.step?.title ?? "", "data-testid": "project-template-step-title" }) }),
      /* @__PURE__ */ jsxRuntime.jsx(Field, { label: "Offset days", children: /* @__PURE__ */ jsxRuntime.jsx("input", { name: "offsetDays", type: "number", defaultValue: templateStepEditor.step?.offsetDays ?? 0, "data-testid": "project-template-step-offset-days" }) }),
      /* @__PURE__ */ jsxRuntime.jsx(Field, { label: "Offset description", children: /* @__PURE__ */ jsxRuntime.jsx("input", { name: "offsetDescription", defaultValue: templateStepEditor.step?.offsetDescription ?? "On anchor date", "data-testid": "project-template-step-offset-description" }) }),
      /* @__PURE__ */ jsxRuntime.jsx(Field, { label: "Assignee", children: /* @__PURE__ */ jsxRuntime.jsxs("select", { name: "assigneeId", defaultValue: templateStepEditor.step?.assigneeId ?? "", "data-testid": "project-template-step-assignee", children: [
        /* @__PURE__ */ jsxRuntime.jsx("option", { value: "", children: "Unassigned" }),
        members.map((person) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: person.id, children: person.name }, person.id))
      ] }) }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => setTemplateStepEditor(null), children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "submit", disabled: mutationPending || !can(templateStepEditor.step ? "projects.update-template-step" : "projects.create-step"), "data-testid": "project-template-step-save", children: "Save step" })
      ] })
    ] }) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: milestoneOpen, onClose: () => setMilestoneOpen(false), title: "Add milestone", description: "Milestones group steps inside this project only.", testId: "project-milestone-dialog", children: /* @__PURE__ */ jsxRuntime.jsxs("form", { className: "project-dialog-form", onSubmit: addMilestone, children: [
      /* @__PURE__ */ jsxRuntime.jsx(Field, { label: "Milestone title", children: /* @__PURE__ */ jsxRuntime.jsx("input", { "data-autofocus": true, name: "title", autoComplete: "off", "data-testid": "project-milestone-title" }) }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => setMilestoneOpen(false), "data-testid": "project-milestone-cancel", children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "submit", "data-testid": "project-milestone-submit", children: "Add milestone" })
      ] })
    ] }) }),
    /* @__PURE__ */ jsxRuntime.jsxs(FocusDialog, { open: Boolean(instanceDelete), onClose: () => setInstanceDelete(null), title: instanceDelete ? `Delete "${instanceDelete.name}"?` : "Delete project?", description: "Only this generated project instance will be removed.", testId: "project-instance-delete-dialog", children: [
      /* @__PURE__ */ jsxRuntime.jsx("p", { className: "delete-copy", children: "The template and neighboring project instances are preserved." }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => setInstanceDelete(null), "data-testid": "project-instance-delete-cancel", children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "danger-button", type: "button", disabled: mutationPending, onClick: () => void confirmDelete(), "data-testid": "project-instance-delete-confirm", children: "Delete project" })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(inspectorStep), onClose: closeInspector, title: inspectorStep?.title ?? "Project step", description: "Project context stays visible while supported step fields are edited.", testId: "project-step-inspector", wide: true, children: inspectorStep && inspectorDraft && /* @__PURE__ */ jsxRuntime.jsx("form", { className: "project-dialog-form inspector-form", onSubmit: saveInspector, children: /* @__PURE__ */ jsxRuntime.jsxs("fieldset", { disabled: mutationPending || !can("projects.update-step"), title: !can("projects.update-step") ? "This host grants inspection only." : void 0, children: [
      /* @__PURE__ */ jsxRuntime.jsx("legend", { className: "sr-only", children: "Project step fields" }),
      /* @__PURE__ */ jsxRuntime.jsx(Field, { label: "Title", children: /* @__PURE__ */ jsxRuntime.jsx("input", { "data-autofocus": true, value: inspectorDraft.title, onChange: (event) => setInspectorDraft({ ...inspectorDraft, title: event.target.value }), "data-testid": "project-step-title" }) }),
      /* @__PURE__ */ jsxRuntime.jsx(Field, { label: "Notes", children: /* @__PURE__ */ jsxRuntime.jsx("textarea", { rows: 4, value: inspectorDraft.notes, onChange: (event) => setInspectorDraft({ ...inspectorDraft, notes: event.target.value }), "data-testid": "project-step-notes" }) }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-grid", children: [
        /* @__PURE__ */ jsxRuntime.jsx(Field, { label: "Scheduled date", children: /* @__PURE__ */ jsxRuntime.jsx("input", { type: "date", value: inspectorDraft.scheduledDate, onChange: (event) => setInspectorDraft({ ...inspectorDraft, scheduledDate: event.target.value }), "data-testid": "project-step-scheduled-date" }) }),
        /* @__PURE__ */ jsxRuntime.jsx(Field, { label: "Due date", children: /* @__PURE__ */ jsxRuntime.jsx("input", { type: "date", value: inspectorDraft.dueDate, onChange: (event) => setInspectorDraft({ ...inspectorDraft, dueDate: event.target.value }), "data-testid": "project-step-due-date" }) })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsx(Field, { label: "Assignee", children: /* @__PURE__ */ jsxRuntime.jsxs("select", { value: inspectorDraft.assigneeId, onChange: (event) => setInspectorDraft({ ...inspectorDraft, assigneeId: event.target.value }), "data-testid": "project-step-assignee", children: [
        /* @__PURE__ */ jsxRuntime.jsx("option", { value: "", children: "Unassigned" }),
        members.map((person) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: person.id, children: person.name }, person.id))
      ] }) }),
      inspectorDraft.scheduledDate && inspectorDraft.dueDate && inspectorDraft.scheduledDate > inspectorDraft.dueDate && /* @__PURE__ */ jsxRuntime.jsx("p", { className: "schedule-warning", role: "status", "data-testid": "project-step-schedule-warning", children: "This step is scheduled after its deadline." }),
      /* @__PURE__ */ jsxRuntime.jsx("div", { className: "dialog-actions", children: /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "submit", disabled: mutationPending, "data-testid": "project-step-save", children: "Save details" }) })
    ] }) }) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: Boolean(operationTarget), onClose: closeOperation, title: "Confirm project operation", description: "Confirm this exact project change before it is sent to the workspace.", testId: "project-operation-confirmation", children: operationTarget && /* @__PURE__ */ jsxRuntime.jsxs(jsxRuntime.Fragment, { children: [
      operationError && /* @__PURE__ */ jsxRuntime.jsx("p", { className: "operation-outcome", role: "alert", "data-testid": "project-operation-outcome", children: "This project changed elsewhere or its result is uncertain. Reload current data or retry with a fresh confirmation." }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
        operationError && /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: mutationPending, onClick: () => {
          closeOperation();
          void load();
        }, "data-testid": "project-operation-reload", children: "Reload" }),
        operationError && /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: mutationPending, onClick: retryOperation, "data-testid": "project-operation-retry", children: "Retry" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: mutationPending, onClick: closeOperation, "data-testid": "project-operation-cancel", children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", disabled: mutationPending, onClick: () => void confirmOperation(), "data-testid": "project-operation-confirm", children: "Confirm" })
      ] })
    ] }) })
  ] }) });
}
var weekdays = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
var months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
function ordinal(day) {
  const mod100 = day % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${day}th`;
  return `${day}${day % 10 === 1 ? "st" : day % 10 === 2 ? "nd" : day % 10 === 3 ? "rd" : "th"}`;
}
function patternDescription(rule) {
  if (rule.frequency === "weekly") return `Every ${weekdays[rule.dayOfWeek] ?? "Monday"}`;
  if (rule.frequency === "monthly") return `Monthly on the ${ordinal(rule.dayOfMonth || 1)}`;
  return `Every ${months[(rule.month || 1) - 1] ?? "January"} ${ordinal(rule.dayOfMonth || 1)}`;
}
function blankDraft() {
  return { title: "", frequency: "weekly", dayOfWeek: 1, dayOfMonth: 1, month: 1, sequential: false, steps: [] };
}
function StatePanel8({ state, onRetry, onCreate }) {
  if (state === "loading") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "rhythms-state", role: "status", "aria-live": "polite", "data-testid": "page-state-loading", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Recurring work" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Loading rhythms" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Gathering recurring rules and workspace members." }),
    /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "rhythms-skeleton", "aria-hidden": "true", children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", {}),
      /* @__PURE__ */ jsxRuntime.jsx("span", {}),
      /* @__PURE__ */ jsxRuntime.jsx("span", {})
    ] })
  ] });
  if (state === "empty") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "rhythms-state", role: "status", "data-testid": "page-state-empty", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "A clear cadence" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "No recurring rules yet" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Create a rhythm to generate the next useful tasks on schedule." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onCreate, "data-testid": "rhythms-empty-create", children: "New rule" })
  ] });
  if (state === "server_error") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "rhythms-state danger", role: "alert", "data-testid": "page-state-server-error", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Retryable server error" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Rhythms could not be loaded" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "The recurring-rule service returned a temporary error. No local changes were lost." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
  ] });
  if (state === "forbidden") return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "rhythms-state warning", role: "alert", "data-testid": "page-state-forbidden", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Workspace permission required" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Rhythms access is restricted" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Ask a workspace administrator for rhythm access." })
  ] });
  return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "rhythms-state warning", role: "status", "data-testid": "page-state-unavailable", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Service prerequisite" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Rhythms are unavailable" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Reconnect the recurring-rule service before loading or changing rhythms." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
  ] });
}
function ScheduleFields({ idPrefix, frequency, dayOfWeek, dayOfMonth, month, disabled = false, onChange }) {
  return /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "rhythm-schedule-fields", children: [
    frequency === "weekly" && /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
      "Day of week",
      /* @__PURE__ */ jsxRuntime.jsx("select", { disabled, value: dayOfWeek, onChange: (event) => onChange({ dayOfWeek: Number(event.target.value) }), "data-testid": `${idPrefix}-day-of-week`, children: weekdays.map((weekday, index) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: index, children: weekday }, weekday)) })
    ] }),
    (frequency === "monthly" || frequency === "annual") && /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
      "Day of month",
      /* @__PURE__ */ jsxRuntime.jsx("input", { type: "number", disabled, min: "1", max: "31", required: true, value: dayOfMonth, onChange: (event) => onChange({ dayOfMonth: Number(event.target.value) }), "data-testid": `${idPrefix}-day-of-month` })
    ] }),
    frequency === "annual" && /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
      "Month",
      /* @__PURE__ */ jsxRuntime.jsx("select", { disabled, value: month, onChange: (event) => onChange({ month: Number(event.target.value) }), "data-testid": `${idPrefix}-month`, children: months.map((monthName, index) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: index + 1, children: monthName }, monthName)) })
    ] })
  ] });
}
function RuleForm({ idPrefix, initial, members, showStepsBuilder = true, disabled = false, onCancel, onSave }) {
  const [draft, setDraft] = react.useState(() => structuredClone(initial));
  const set = (key, value) => setDraft((current) => ({ ...current, [key]: value }));
  const addStep = () => setDraft((current) => ({ ...current, steps: [...current.steps, { title: "", assigneeId: "" }] }));
  const patchStep = (index, patch) => setDraft((current) => ({ ...current, steps: current.steps.map((step, stepIndex) => stepIndex === index ? { ...step, ...patch } : step) }));
  const removeStep = (index) => setDraft((current) => ({ ...current, steps: current.steps.filter((_, stepIndex) => stepIndex !== index) }));
  const moveStep = (index, direction) => setDraft((current) => {
    const destination = index + direction;
    if (destination < 0 || destination >= current.steps.length) return current;
    const steps = [...current.steps];
    [steps[index], steps[destination]] = [steps[destination], steps[index]];
    return { ...current, steps };
  });
  const submit = (event) => {
    event.preventDefault();
    const title = draft.title.trim();
    if (!title) return;
    onSave({ ...draft, title, steps: draft.steps.filter((step) => step.title.trim()).map((step) => ({ ...step, title: step.title.trim() })) });
  };
  return /* @__PURE__ */ jsxRuntime.jsxs("form", { className: "rhythm-rule-form", onSubmit: submit, children: [
    /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
      "Title",
      /* @__PURE__ */ jsxRuntime.jsx("input", { "data-autofocus": true, required: true, disabled, value: draft.title, onChange: (event) => set("title", event.target.value), "data-testid": `${idPrefix}-title` })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
      "Frequency",
      /* @__PURE__ */ jsxRuntime.jsxs("select", { disabled, value: draft.frequency, onChange: (event) => set("frequency", event.target.value), "data-testid": `${idPrefix}-frequency`, children: [
        /* @__PURE__ */ jsxRuntime.jsx("option", { value: "weekly", children: "Weekly" }),
        /* @__PURE__ */ jsxRuntime.jsx("option", { value: "monthly", children: "Monthly" }),
        /* @__PURE__ */ jsxRuntime.jsx("option", { value: "annual", children: "Annual" })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsx(ScheduleFields, { idPrefix, frequency: draft.frequency, dayOfWeek: draft.dayOfWeek, dayOfMonth: draft.dayOfMonth, month: draft.month, disabled, onChange: (patch) => setDraft((current) => ({ ...current, ...patch })) }),
    showStepsBuilder && /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "rhythm-step-section", "aria-labelledby": `${idPrefix}-steps-heading`, children: [
      /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
        /* @__PURE__ */ jsxRuntime.jsx("h3", { id: `${idPrefix}-steps-heading`, children: "Workflow steps" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled, onClick: addStep, "data-testid": `${idPrefix}-add-step`, children: "Add step" })
      ] }),
      draft.steps.length === 0 && /* @__PURE__ */ jsxRuntime.jsx("p", { className: "rhythm-step-empty", children: "No workflow steps. The rhythm can still generate its own task." }),
      draft.steps.map((step, index) => /* @__PURE__ */ jsxRuntime.jsxs("fieldset", { className: "rhythm-step", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("legend", { children: [
          "Step ",
          index + 1
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
          "Task title",
          /* @__PURE__ */ jsxRuntime.jsx("input", { disabled, value: step.title, onChange: (event) => patchStep(index, { title: event.target.value }), "data-testid": `${idPrefix}-step-title-${index}` })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
          "Assignee",
          /* @__PURE__ */ jsxRuntime.jsxs("select", { disabled, value: step.assigneeId, onChange: (event) => patchStep(index, { assigneeId: event.target.value }), "data-testid": `${idPrefix}-step-assignee-${index}`, children: [
            /* @__PURE__ */ jsxRuntime.jsx("option", { value: "", children: "None" }),
            members.map((person) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: person.id, children: person.name }, person.id))
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-danger-button", type: "button", disabled, onClick: () => removeStep(index), "data-testid": `${idPrefix}-remove-step-${index}`, children: "Remove step" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-button", type: "button", disabled: disabled || index === 0, onClick: () => moveStep(index, -1), "data-testid": `${idPrefix}-move-step-up-${index}`, children: "Move up" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-button", type: "button", disabled: disabled || index === draft.steps.length - 1, onClick: () => moveStep(index, 1), "data-testid": `${idPrefix}-move-step-down-${index}`, children: "Move down" })
      ] }, index)),
      draft.steps.length > 1 && /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "rhythm-sequential", children: [
        /* @__PURE__ */ jsxRuntime.jsx("input", { type: "checkbox", disabled, checked: draft.sequential, onChange: (event) => set("sequential", event.target.checked), "data-testid": `${idPrefix}-sequential` }),
        /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
          /* @__PURE__ */ jsxRuntime.jsx("strong", { children: "Sequential" }),
          /* @__PURE__ */ jsxRuntime.jsx("small", { children: "Generate each step after the previous one completes." })
        ] })
      ] })
    ] }),
    !showStepsBuilder && draft.steps.length > 1 && /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "rhythm-sequential", children: [
      /* @__PURE__ */ jsxRuntime.jsx("input", { type: "checkbox", disabled, checked: draft.sequential, onChange: (event) => set("sequential", event.target.checked), "data-testid": `${idPrefix}-sequential` }),
      /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
        /* @__PURE__ */ jsxRuntime.jsx("strong", { children: "Sequential" }),
        /* @__PURE__ */ jsxRuntime.jsx("small", { children: "Generate each step after the previous one completes." })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("footer", { className: "dialog-actions", children: [
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: onCancel, "data-testid": `${idPrefix}-cancel`, children: "Cancel" }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "submit", disabled, "data-testid": `${idPrefix}-submit`, children: idPrefix === "rhythm-create" ? "Create rule" : "Save rule" })
    ] })
  ] });
}
function RhythmsScreen() {
  const { rhythms: gateway } = useRhythmDomainGateway();
  const host = useRhythmHost();
  const capabilities = host.currentUser.capabilities ?? [];
  const can = (operation) => capabilities.includes("rhythms.write") || capabilities.includes(operation);
  const isOwner = (rule) => Boolean(host.currentUser.id && host.currentUser.id === rule.ownerId);
  const [surfaceState, setSurfaceState] = react.useState("loading");
  const [rules, setRules] = react.useState([]);
  const [members, setMembers] = react.useState([]);
  const [selectedId, setSelectedId] = react.useState(null);
  const [createOpen, setCreateOpen] = react.useState(false);
  const [stepTitle, setStepTitle] = react.useState("");
  const [stepAssignee, setStepAssignee] = react.useState("");
  const [mutationPending, setMutationPending] = react.useState(false);
  const [operationTarget, setOperationTarget] = react.useState(null);
  const [operationError, setOperationError] = react.useState(null);
  const newRuleTriggerRef = react.useRef(null);
  const loadGeneration = react.useRef(0);
  const operationGeneration = react.useRef(0);
  const operationEpoch = react.useRef(0);
  const mounted = react.useRef(true);
  const selected = rules.find((rule) => rule.id === selectedId) ?? null;
  const handleError = (error) => {
    const kind = error instanceof RhythmGatewayError ? error.kind : "server_error";
    setSurfaceState(kind === "forbidden" ? "forbidden" : kind === "not_found" ? "unavailable" : kind === "unavailable" ? "unavailable" : "server_error");
  };
  const load = async () => {
    const generation = ++loadGeneration.current;
    setSurfaceState("loading");
    try {
      const [loadedRules, loadedMembers] = await Promise.all([gateway.list(), gateway.members()]);
      if (generation !== loadGeneration.current) return;
      setRules(loadedRules);
      setMembers(loadedMembers);
      setSurfaceState(loadedRules.length ? "ready" : "empty");
    } catch (error) {
      if (generation === loadGeneration.current) handleError(error);
    }
  };
  react.useEffect(() => {
    void load();
    return () => {
      loadGeneration.current += 1;
    };
  }, [gateway]);
  react.useEffect(() => () => {
    mounted.current = false;
    operationEpoch.current += 1;
  }, []);
  const showsWorkspace = surfaceState === "ready";
  const closeOperation = () => {
    operationEpoch.current += 1;
    setOperationError(null);
    setOperationTarget(null);
  };
  const inspect = (rule) => {
    closeOperation();
    setSelectedId(rule.id);
  };
  const closeSelection = () => {
    closeOperation();
    setSelectedId(null);
  };
  const requestOperation = (operation, entityId, payload, mutate) => {
    if (!can(operation) || mutationPending) return;
    operationGeneration.current += 1;
    operationEpoch.current += 1;
    setOperationError(null);
    setOperationTarget({ operation, entityId, payload, mutate, generation: `${entityId}:${operation}:${operationGeneration.current}:${Date.now()}` });
  };
  const retryOperation = () => {
    if (!operationTarget || mutationPending) return;
    operationGeneration.current += 1;
    operationEpoch.current += 1;
    setOperationError(null);
    setOperationTarget((target) => target && { ...target, generation: `${target.entityId}:${target.operation}:${operationGeneration.current}:${Date.now()}` });
  };
  const confirmOperation = async () => {
    if (!operationTarget || mutationPending) return;
    const target = operationTarget;
    const epoch = operationEpoch.current;
    setMutationPending(true);
    try {
      const confirmation = { operation: target.operation, entityId: target.entityId, payload: target.payload, generation: target.generation };
      if (host.confirmWorkspaceOperation && !await host.confirmWorkspaceOperation(confirmation)) return;
      if (!mounted.current || operationEpoch.current !== epoch || operationTarget !== target) return;
      await target.mutate();
      if (!mounted.current || operationEpoch.current !== epoch || operationTarget !== target) return;
      setOperationTarget(null);
    } catch (error) {
      const kind = error?.kind;
      if (kind === "conflict" || kind === "uncertain") setOperationError(kind);
      else handleError(error);
    } finally {
      if (mounted.current) setMutationPending(false);
    }
  };
  const toggleEnabled = async (rule, enabled) => {
    if (!isOwner(rule)) return;
    requestOperation("rhythms.update-rule", rule.id, { enabled }, async () => {
      const updated = await gateway.update(rule.id, { enabled });
      setRules((current) => current.map((item) => item.id === rule.id ? updated : item));
    });
  };
  const createRule = async (draft) => {
    const normalizedSteps = draft.steps.map((step) => ({ title: step.title.trim().slice(0, 200), assigneeId: step.assigneeId || null }));
    const input = { title: draft.title.slice(0, 200), frequency: draft.frequency, dayOfWeek: draft.dayOfWeek, dayOfMonth: draft.dayOfMonth, month: draft.month, sequential: draft.sequential, steps: normalizedSteps };
    requestOperation("rhythms.create-rule", "new-rule", input, async () => {
      const created = await gateway.create(input);
      setRules((current) => [...current, created]);
      setSelectedId(created.id);
      setCreateOpen(false);
    });
  };
  const saveRule = async (draft) => {
    if (!selected || !isOwner(selected)) return;
    const steps = draft.steps.map((step) => ({ title: step.title.trim(), assigneeId: step.assigneeId || "" }));
    const originalSteps = selected.steps.map((step) => ({ title: step.title, assigneeId: step.assigneeId ?? "" }));
    const sameStep = (left, right) => left.title === right.title && left.assigneeId === right.assigneeId;
    const sameStepSet = JSON.stringify([...steps].sort((left, right) => `${left.title}:${left.assigneeId}`.localeCompare(`${right.title}:${right.assigneeId}`))) === JSON.stringify([...originalSteps].sort((left, right) => `${left.title}:${left.assigneeId}`.localeCompare(`${right.title}:${right.assigneeId}`)));
    const ruleChanged = selected.title !== draft.title || selected.frequency !== draft.frequency || selected.dayOfWeek !== draft.dayOfWeek || selected.dayOfMonth !== draft.dayOfMonth || selected.month !== draft.month || selected.sequential !== draft.sequential;
    const stepsChanged = JSON.stringify(steps) !== JSON.stringify(originalSteps);
    const operation = ruleChanged ? "rhythms.update-rule" : steps.length > originalSteps.length ? "rhythms.create-step" : steps.length < originalSteps.length ? "rhythms.delete-step" : sameStepSet && steps.some((step, index) => !sameStep(step, originalSteps[index])) ? "rhythms.reorder-step" : "rhythms.update-step";
    if (!ruleChanged && !stepsChanged) return;
    requestOperation(operation, selected.id, { title: draft.title.slice(0, 200), frequency: draft.frequency, dayOfWeek: draft.dayOfWeek, dayOfMonth: draft.dayOfMonth, month: draft.month, sequential: draft.sequential, steps: JSON.stringify(steps.map((step) => ({ title: step.title.slice(0, 200), assigneeId: step.assigneeId || null }))).slice(0, 2e3) }, async () => {
      let updated = selected;
      if (ruleChanged) updated = await gateway.update(selected.id, { title: draft.title, frequency: draft.frequency, dayOfWeek: draft.dayOfWeek, dayOfMonth: draft.dayOfMonth, month: draft.month, sequential: draft.sequential });
      if (stepsChanged) updated = await gateway.replaceSteps(selected.id, steps.map((step) => ({ title: step.title, assigneeId: step.assigneeId || void 0 })));
      setRules((current) => current.map((rule) => rule.id === selected.id ? updated : rule));
    });
  };
  const addWorkflowStep = async (event) => {
    event.preventDefault();
    if (!selected || !isOwner(selected) || !stepTitle.trim()) return;
    requestOperation("rhythms.create-step", selected.id, { title: stepTitle.trim().slice(0, 200), assigneeId: stepAssignee || null }, async () => {
      const step = await gateway.addStep(selected.id, { title: stepTitle.trim(), assigneeId: stepAssignee || void 0 });
      setRules((current) => current.map((rule) => rule.id === selected.id ? { ...rule, steps: [...rule.steps, step] } : rule));
      setStepTitle("");
      setStepAssignee("");
    });
  };
  return /* @__PURE__ */ jsxRuntime.jsx(ScreenRoot, { screenName: "Rhythms", testId: "rhythm-rhythms-screen", children: /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "page-shell pg-rhythms", "aria-busy": surfaceState === "loading", children: [
    /* @__PURE__ */ jsxRuntime.jsxs("header", { className: "rhythms-header", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "rhythms-heading", children: [
        /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Recurring work" }),
        /* @__PURE__ */ jsxRuntime.jsx("h1", { children: "Rhythms" }),
        /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Manage recurring rules, owners, generated tasks, and the next scheduled run." })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "rhythms-header-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("span", { "data-testid": "rhythms-visible-count", children: [
          rules.length,
          " ",
          rules.length === 1 ? "rule" : "rules"
        ] }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { ref: newRuleTriggerRef, className: "primary-button", type: "button", disabled: !showsWorkspace || !can("rhythms.create-rule"), title: !can("rhythms.create-rule") ? "This host grants inspection only." : void 0, onClick: () => setCreateOpen(true), "data-testid": "rhythms-new-rule", children: "New rule" })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "rhythms-scroll", children: [
      !showsWorkspace && /* @__PURE__ */ jsxRuntime.jsx(StatePanel8, { state: surfaceState, onRetry: () => void load(), onCreate: () => setCreateOpen(true) }),
      showsWorkspace && /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "rhythms-layout", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "rhythms-collection", "aria-labelledby": "rhythms-list-title", children: [
          /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "rhythms-list-title", children: "Recurring rules" }),
          /* @__PURE__ */ jsxRuntime.jsx("div", { className: "rhythms-list", "data-testid": "rhythms-list", children: rules.map((rule) => /* @__PURE__ */ jsxRuntime.jsxs("article", { className: `rhythm-card ${rule.enabled ? "" : "paused"}`, "data-testid": `rhythm-card-${rule.id}`, children: [
            /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "rhythm-card-copy", children: [
              /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", "data-testid": `rhythm-status-${rule.id}`, children: rule.enabled ? "Enabled" : "Paused" }),
              /* @__PURE__ */ jsxRuntime.jsx("h3", { children: rule.title }),
              /* @__PURE__ */ jsxRuntime.jsx("p", { "data-testid": `rhythm-pattern-${rule.id}`, children: patternDescription(rule) })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "rhythm-card-actions", children: [
              /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", "aria-label": `Inspect ${rule.title}`, onClick: () => inspect(rule), "data-testid": `rhythm-inspect-${rule.id}`, children: "Inspect" }),
              /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "rhythm-enabled-toggle", children: [
                /* @__PURE__ */ jsxRuntime.jsx("input", { type: "checkbox", checked: rule.enabled, disabled: mutationPending || !can("rhythms.update-rule") || !isOwner(rule), title: !isOwner(rule) ? "Only the rhythm owner can change this rule." : !can("rhythms.update-rule") ? "This host grants inspection only." : void 0, "aria-label": `${rule.enabled ? "Enabled" : "Paused"} - ${rule.title}`, onChange: (event) => void toggleEnabled(rule, event.target.checked), "data-testid": `rhythm-enabled-${rule.id}` }),
                /* @__PURE__ */ jsxRuntime.jsx("span", { "aria-hidden": "true" }),
                /* @__PURE__ */ jsxRuntime.jsx("b", { children: rule.enabled ? "Enabled" : "Paused" })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-danger-button", type: "button", disabled: mutationPending || !can("rhythms.delete-rule") || !isOwner(rule), title: !isOwner(rule) ? "Only the rhythm owner can delete this rule." : !can("rhythms.delete-rule") ? "This host grants inspection only." : void 0, "aria-label": `Delete ${rule.title}`, onClick: () => requestOperation("rhythms.delete-rule", rule.id, { title: rule.title.slice(0, 200) }, async () => {
                await gateway.delete(rule.id);
                setRules((current) => current.filter((item) => item.id !== rule.id));
                if (selectedId === rule.id) setSelectedId(null);
              }), "data-testid": `rhythm-delete-${rule.id}`, children: "Delete" })
            ] })
          ] }, rule.id)) })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsx("aside", { className: "rhythms-detail-column", "aria-label": "Selected rhythm", children: selected ? /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "rhythm-detail", "aria-labelledby": "rhythm-detail-title", "data-testid": "rhythm-detail", children: [
          /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
            /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: selected.enabled ? "Enabled rhythm" : "Paused rhythm" }),
              /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "rhythm-detail-title", children: selected.title }),
              /* @__PURE__ */ jsxRuntime.jsx("p", { children: patternDescription(selected) })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-button", type: "button", onClick: closeSelection, "data-testid": "rhythm-detail-close", children: "Close" })
          ] }),
          /* @__PURE__ */ jsxRuntime.jsxs("dl", { className: "rhythm-metrics", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Owner" }),
              /* @__PURE__ */ jsxRuntime.jsx("dd", { "data-testid": "rhythm-owner", children: selected.ownerName })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Generated" }),
              /* @__PURE__ */ jsxRuntime.jsxs("dd", { "data-testid": "rhythm-generated-count", children: [
                selected.generatedCount,
                " generated tasks"
              ] })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Completed" }),
              /* @__PURE__ */ jsxRuntime.jsxs("dd", { "data-testid": "rhythm-completed-count", children: [
                selected.completedCount,
                " completed"
              ] })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("dt", { children: "Remaining" }),
              /* @__PURE__ */ jsxRuntime.jsxs("dd", { "data-testid": "rhythm-remaining-count", children: [
                selected.remainingCount,
                " remaining"
              ] })
            ] })
          ] }),
          /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "rhythm-next", children: [
            /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Next due" }),
            /* @__PURE__ */ jsxRuntime.jsx("strong", { "data-testid": "rhythm-next-due", children: selected.enabled ? selected.nextDueDate ?? "Not scheduled" : "Paused - no next generation" }),
            /* @__PURE__ */ jsxRuntime.jsx("p", { "data-testid": "rhythm-waiting-on", children: selected.waitingOn ? `Waiting on ${selected.waitingOn}` : "No person is blocking the next task" })
          ] }),
          /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "rhythm-edit", "aria-labelledby": "rhythm-edit-title", children: [
            /* @__PURE__ */ jsxRuntime.jsx("h3", { id: "rhythm-edit-title", children: "Edit rhythm" }),
            /* @__PURE__ */ jsxRuntime.jsx(
              RuleForm,
              {
                idPrefix: "rhythm-edit",
                showStepsBuilder: true,
                initial: { title: selected.title, frequency: selected.frequency, dayOfWeek: selected.dayOfWeek, dayOfMonth: selected.dayOfMonth, month: selected.month, sequential: selected.sequential, steps: selected.steps.map((step) => ({ title: step.title, assigneeId: step.assigneeId ?? "" })) },
                members,
                disabled: mutationPending || !isOwner(selected) || !["rhythms.update-rule", "rhythms.create-step", "rhythms.update-step", "rhythms.delete-step", "rhythms.reorder-step"].some(can),
                onCancel: closeSelection,
                onSave: (draft) => void saveRule(draft)
              }
            )
          ] }),
          /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "rhythm-collaborators", "aria-labelledby": "rhythm-collaborators-title", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
              /* @__PURE__ */ jsxRuntime.jsx("h3", { id: "rhythm-collaborators-title", children: "Collaborators" }),
              /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: true, title: "Collaborator changes are not available from this host-neutral surface.", "data-testid": "rhythm-add-collaborator", children: "Add collaborator" })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsx("div", { className: "rhythm-people", children: selected.collaborators.length ? selected.collaborators.map((person) => /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "rhythm-person", "data-testid": `rhythm-collaborator-${person.id}`, children: [
              /* @__PURE__ */ jsxRuntime.jsx("span", { "aria-hidden": "true", children: person.initials }),
              /* @__PURE__ */ jsxRuntime.jsx("strong", { children: person.name }),
              /* @__PURE__ */ jsxRuntime.jsx("button", { type: "button", disabled: true, "aria-label": `Remove ${person.name}`, title: "Collaborator changes are not available from this host-neutral surface.", "data-testid": `rhythm-remove-collaborator-${person.id}`, children: "Remove" })
            ] }, person.id)) : /* @__PURE__ */ jsxRuntime.jsx("p", { children: "No collaborators yet." }) })
          ] }),
          /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "rhythm-detail-steps", "aria-labelledby": "rhythm-steps-title", children: [
            /* @__PURE__ */ jsxRuntime.jsx("h3", { id: "rhythm-steps-title", children: "Workflow steps" }),
            selected.steps.length > 0 && /* @__PURE__ */ jsxRuntime.jsx("ol", { children: selected.steps.map((step) => /* @__PURE__ */ jsxRuntime.jsxs("li", { "data-testid": `rhythm-step-${step.id}`, children: [
              /* @__PURE__ */ jsxRuntime.jsx("strong", { children: step.title }),
              /* @__PURE__ */ jsxRuntime.jsx("span", { children: members.find((person) => person.id === step.assigneeId)?.name ?? "Unassigned" })
            ] }, step.id)) }),
            /* @__PURE__ */ jsxRuntime.jsxs("form", { className: "rhythm-add-step-form", onSubmit: addWorkflowStep, children: [
              /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
                "New step title",
                /* @__PURE__ */ jsxRuntime.jsx("input", { disabled: !can("rhythms.create-step") || !isOwner(selected), value: stepTitle, onChange: (event) => setStepTitle(event.target.value), "data-testid": "rhythm-add-step-title" })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
                "Assignee",
                /* @__PURE__ */ jsxRuntime.jsxs("select", { disabled: !can("rhythms.create-step") || !isOwner(selected), value: stepAssignee, onChange: (event) => setStepAssignee(event.target.value), "data-testid": "rhythm-add-step-assignee", children: [
                  /* @__PURE__ */ jsxRuntime.jsx("option", { value: "", children: "None" }),
                  members.map((person) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: person.id, children: person.name }, person.id))
                ] })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "submit", disabled: mutationPending || !can("rhythms.create-step") || !isOwner(selected) || !stepTitle.trim(), "data-testid": "rhythm-add-step-submit", children: "Add step" })
            ] })
          ] })
        ] }) : /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "rhythm-detail-empty", "aria-labelledby": "rhythm-detail-empty-title", children: [
          /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "rhythm-detail-empty-title", children: "Select a rhythm" }),
          /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Inspect ownership, generated work, and the next due task without leaving the collection." })
        ] }) })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: createOpen, onClose: () => {
      closeOperation();
      setCreateOpen(false);
    }, title: "New Recurring Rule", description: "Create a recurring rule with optional workflow steps.", testId: "rhythm-create-dialog", wide: true, children: /* @__PURE__ */ jsxRuntime.jsx(RuleForm, { idPrefix: "rhythm-create", initial: blankDraft(), members, disabled: mutationPending || !can("rhythms.create-rule"), onCancel: () => {
      closeOperation();
      setCreateOpen(false);
    }, onSave: (draft) => void createRule(draft) }) }),
    /* @__PURE__ */ jsxRuntime.jsxs(FocusDialog, { open: Boolean(operationTarget), onClose: closeOperation, title: "Confirm Rhythm change", description: "This exact change is sent only after you confirm it.", testId: "rhythm-operation-confirmation", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("p", { role: "status", children: [
        "Confirm ",
        operationTarget?.operation,
        " for this rhythm."
      ] }),
      operationError && /* @__PURE__ */ jsxRuntime.jsxs("div", { role: "alert", "data-testid": "rhythm-operation-outcome", children: [
        /* @__PURE__ */ jsxRuntime.jsx("p", { children: operationError === "conflict" ? "This rhythm changed elsewhere. Reload before retrying." : "We could not verify whether this change was applied. Reload before retrying." }),
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => void load(), "data-testid": "rhythm-operation-reload", children: "Reload" }),
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: retryOperation, "data-testid": "rhythm-operation-retry", children: "Retry" })
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: closeOperation, "data-testid": "rhythm-operation-cancel", children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", disabled: mutationPending, onClick: () => void confirmOperation(), "data-autofocus": true, "data-testid": "rhythm-operation-confirm", children: "Confirm" })
      ] })
    ] })
  ] }) });
}
var boardStatuses = ["open", "in_progress", "waiting_for_reply", "done"];
var taskStatusLabels = { open: "Open", in_progress: "In progress", waiting_for_reply: "Waiting for reply", done: "Done" };
var bucketOrder = ["past-due", "today", "week", "month", "no-due", "completed"];
var bucketLabels = { "past-due": "Past due", today: "Today", week: "This week", month: "This month", "no-due": "No date", completed: "Completed" };
function dateLabel(task) {
  if (task.bucket === "past-due") return "Past due";
  if (task.bucket === "today") return "Today";
  return task.scheduledDate ?? task.dueDate ?? "No date";
}
function isSourceReadonly(task) {
  return task.sourceType === "calendar_shadow_event" || task.sourceType === "prod_mirror";
}
function StatePanel9({ state, onRetry, onEmpty, canWrite }) {
  if (state === "loading") {
    return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "tasks-state loading", role: "status", "aria-live": "polite", "data-testid": "page-state-loading", children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Current workspace" }),
      /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Loading tasks" }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Gathering the current task list." }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "tasks-skeleton state-skeleton", "aria-hidden": "true", children: [
        /* @__PURE__ */ jsxRuntime.jsx("span", {}),
        /* @__PURE__ */ jsxRuntime.jsx("span", {}),
        /* @__PURE__ */ jsxRuntime.jsx("span", {})
      ] })
    ] });
  }
  if (state === "empty") {
    return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "tasks-state", role: "status", "data-testid": "page-state-empty", children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "A clear workspace" }),
      /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "No tasks yet" }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Create a task above and it will settle into this workspace." }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", disabled: !canWrite, onClick: onEmpty, "data-testid": "tasks-empty-create", children: "Create a task" })
    ] });
  }
  if (state === "server_error") {
    return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "tasks-state danger", role: "alert", "data-testid": "page-state-server-error", children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Retryable server error" }),
      /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Unable to load tasks" }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { children: "The task service returned a temporary failure. Your source data remains unchanged." }),
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
    ] });
  }
  if (state === "forbidden") {
    return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "tasks-state warning", role: "alert", "data-testid": "page-state-forbidden", children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Workspace permission required" }),
      /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Tasks access is restricted" }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Ask a workspace administrator for task access." })
    ] });
  }
  return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "tasks-state warning", role: "status", "data-testid": "page-state-unavailable", children: [
    /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Service prerequisite" }),
    /* @__PURE__ */ jsxRuntime.jsx("h2", { children: "Tasks are unavailable" }),
    /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Reconnect the task service before loading or changing this queue." }),
    /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", onClick: onRetry, "data-testid": "page-retry", children: "Retry" })
  ] });
}
function TaskMenu({ task, readonly, isOwner, ownerOnlyReasonId, readonlyReasonId, onInspect, onDelete }) {
  const [open, setOpen] = react.useState(false);
  const rootRef = react.useRef(null);
  const triggerRef = react.useRef(null);
  react.useEffect(() => {
    if (!open) return;
    const closeOutside = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    };
    const closeWithEscape = (event) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener("mousedown", closeOutside);
    document.addEventListener("keydown", closeWithEscape);
    requestAnimationFrame(() => rootRef.current?.querySelector('[role="menuitem"]:not([disabled])')?.focus());
    return () => {
      document.removeEventListener("mousedown", closeOutside);
      document.removeEventListener("keydown", closeWithEscape);
    };
  }, [open]);
  const moveFocus = (event) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const items = [...event.currentTarget.querySelectorAll('[role="menuitem"]:not([disabled])')];
    if (!items.length) return;
    event.preventDefault();
    const current = Math.max(0, items.indexOf(document.activeElement));
    const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (current + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    items[next]?.focus();
  };
  return /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "task-menu-anchor", ref: rootRef, children: [
    /* @__PURE__ */ jsxRuntime.jsx("button", { ref: triggerRef, className: "icon-button task-menu-trigger", type: "button", "aria-label": `Actions for ${task.title}`, "aria-haspopup": "menu", "aria-expanded": open, onClick: () => setOpen((value) => !value), "data-testid": `task-menu-${task.id}`, children: /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "more", size: 16 }) }),
    open && /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "menu-popover task-menu", role: "menu", "aria-label": `Actions for ${task.title}`, onKeyDown: moveFocus, children: [
      /* @__PURE__ */ jsxRuntime.jsx("button", { className: "menu-item", role: "menuitem", type: "button", onClick: () => {
        setOpen(false);
        onInspect();
      }, "data-testid": `task-menu-inspect-${task.id}`, children: "Inspect task" }),
      /* @__PURE__ */ jsxRuntime.jsx(
        "button",
        {
          className: "menu-item danger-item",
          role: "menuitem",
          type: "button",
          disabled: !isOwner || readonly,
          "aria-describedby": !isOwner ? ownerOnlyReasonId : readonly ? readonlyReasonId : void 0,
          onClick: () => {
            setOpen(false);
            onDelete();
          },
          "data-testid": `task-delete-${task.id}`,
          children: "Delete task"
        }
      )
    ] })
  ] });
}
function TasksScreen() {
  const { tasks: gateway } = useRhythmDomainGateway();
  const host = useRhythmHost();
  const canWrite = host.currentUser.capabilities?.includes("tasks.write") ?? false;
  const canComplete = canWrite || (host.currentUser.capabilities?.includes("tasks.complete") ?? false);
  const canReschedule = canWrite || (host.currentUser.capabilities?.includes("tasks.reschedule") ?? false);
  const [surfaceState, setSurfaceState] = react.useState("loading");
  const [tasks, setTasks] = react.useState([]);
  const [members, setMembers] = react.useState([]);
  const [view, setView] = react.useState("list");
  const [selectedId, setSelectedId] = react.useState(null);
  const [search, setSearch] = react.useState("");
  const [tag, setTag] = react.useState("all");
  const [minimumPriority, setMinimumPriority] = react.useState("0");
  const [completion, setCompletion] = react.useState("open");
  const [dateWindow, setDateWindow] = react.useState("all");
  const [sort, setSort] = react.useState("due");
  const [deleteTarget, setDeleteTarget] = react.useState(null);
  const [collaboratorPickerOpen, setCollaboratorPickerOpen] = react.useState(false);
  const [createOpen, setCreateOpen] = react.useState(false);
  const [draggedId, setDraggedId] = react.useState(null);
  const [mutationPending, setMutationPending] = react.useState(false);
  const [operationTarget, setOperationTarget] = react.useState(null);
  const [operationError, setOperationError] = react.useState(null);
  const createTitleRef = react.useRef(null);
  const operationGeneration = react.useRef(0);
  const operationEpoch = react.useRef(0);
  const mounted = react.useRef(true);
  react.useEffect(() => () => {
    mounted.current = false;
    operationEpoch.current += 1;
  }, []);
  const currentUserId = host.currentUser.initials;
  const handleError = (error) => {
    const kind = error instanceof RhythmGatewayError ? error.kind : "server_error";
    setSurfaceState(kind === "forbidden" ? "forbidden" : kind === "not_found" ? "unavailable" : kind === "unavailable" ? "unavailable" : "server_error");
  };
  const load = async () => {
    setSurfaceState("loading");
    try {
      const [loadedTasks, loadedMembers] = await Promise.all([gateway.list(), gateway.members()]);
      setTasks(loadedTasks);
      setMembers(loadedMembers);
      setSurfaceState(loadedTasks.length ? "ready" : "empty");
    } catch (error) {
      handleError(error);
    }
  };
  react.useEffect(() => {
    void load();
  }, [gateway]);
  const selectedTask = tasks.find((task) => task.id === selectedId) ?? null;
  const showsWorkspace = surfaceState === "ready";
  const ownerOnlyReasonId = "tasks-owner-only-reason";
  const readonlyReasonId = "tasks-readonly-reason";
  const tagOptions = react.useMemo(() => [...new Set(tasks.flatMap((task) => task.tags))].sort(), [tasks]);
  const visibleTasks = react.useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    const priority = Number(minimumPriority);
    const filtered = tasks.filter((task) => {
      if (needle && ![task.title, task.notes, task.sourceName ?? ""].some((value) => value.toLocaleLowerCase().includes(needle))) return false;
      if (tag !== "all" && !task.tags.includes(tag)) return false;
      if (task.priority < priority) return false;
      if (view === "list" && completion === "open" && task.status === "done") return false;
      if (dateWindow !== "all" && task.bucket !== dateWindow) return false;
      return true;
    });
    const statusOrder = ["open", "in_progress", "waiting_for_reply", "done"];
    return [...filtered].sort((left, right) => {
      if (sort === "title") return left.title.localeCompare(right.title, void 0, { sensitivity: "base" });
      if (sort === "created") return left.createdAt.localeCompare(right.createdAt);
      if (sort === "status") return statusOrder.indexOf(left.status) - statusOrder.indexOf(right.status) || left.title.localeCompare(right.title);
      const leftDate = left.dueDate ?? left.scheduledDate ?? "9999-12-31";
      const rightDate = right.dueDate ?? right.scheduledDate ?? "9999-12-31";
      return leftDate.localeCompare(rightDate) || left.title.localeCompare(right.title);
    });
  }, [completion, dateWindow, minimumPriority, search, sort, tag, tasks, view]);
  const groupedTasks = react.useMemo(
    () => bucketOrder.map((bucket) => ({ bucket, tasks: visibleTasks.filter((task) => task.bucket === bucket) })).filter((group) => group.tasks.length > 0),
    [visibleTasks]
  );
  const openInspector = (task) => setSelectedId(task.id);
  const closeInspector = () => setSelectedId(null);
  const changeStatus = async (task, nextStatus) => {
    if (!canWrite || mutationPending) return;
    setMutationPending(true);
    try {
      const updated = await gateway.update(task.id, { status: nextStatus });
      setTasks((current) => current.map((item) => item.id === task.id ? updated : item));
    } catch (error) {
      handleError(error);
    } finally {
      setMutationPending(false);
    }
  };
  const requestTaskOperation = (task, operation) => {
    if (operation === "complete" && !canComplete || operation === "reschedule" && !canReschedule || mutationPending) return;
    operationGeneration.current += 1;
    operationEpoch.current += 1;
    setOperationError(null);
    setOperationTarget({ task, operation, scheduledDate: operation === "reschedule" ? task.scheduledDate ?? (/* @__PURE__ */ new Date()).toISOString().slice(0, 10) : void 0, generation: `${task.id}:${operation}:${operationGeneration.current}:${Date.now()}` });
  };
  const retryTaskOperation = () => {
    if (!operationTarget || mutationPending) return;
    operationGeneration.current += 1;
    operationEpoch.current += 1;
    setOperationError(null);
    setOperationTarget((target) => target && { ...target, generation: `${target.task.id}:${target.operation}:${operationGeneration.current}:${Date.now()}` });
  };
  const reloadTaskOperationContext = async () => {
    try {
      const [loadedTasks, loadedMembers] = await Promise.all([gateway.list(), gateway.members()]);
      setTasks(loadedTasks);
      setMembers(loadedMembers);
      setSurfaceState(loadedTasks.length ? "ready" : "empty");
    } catch (error) {
      handleError(error);
    }
  };
  const isIsoCalendarDate = (value) => Boolean(value && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`)) && (/* @__PURE__ */ new Date(`${value}T00:00:00Z`)).toISOString().slice(0, 10) === value);
  const confirmTaskOperation = async () => {
    if (!operationTarget || mutationPending) return;
    if (operationTarget.operation === "reschedule" && !isIsoCalendarDate(operationTarget.scheduledDate)) {
      handleError(new RhythmGatewayError("server_error", "Choose a real calendar date."));
      return;
    }
    const confirmation = { taskId: operationTarget.task.id, generation: operationTarget.generation, operation: operationTarget.operation, scheduledDate: operationTarget.scheduledDate };
    const target = operationTarget;
    const epoch = operationEpoch.current;
    setMutationPending(true);
    try {
      if (host.confirmTaskOperation && !await host.confirmTaskOperation(confirmation)) return;
      if (!mounted.current || operationEpoch.current !== epoch || operationTarget !== target) return;
      const updated = target.operation === "complete" ? gateway.complete ? await gateway.complete(target.task.id, target.generation) : canWrite ? await gateway.update(target.task.id, { status: "done" }) : null : gateway.reschedule && target.scheduledDate ? await gateway.reschedule(target.task.id, target.scheduledDate, target.generation) : canWrite && target.scheduledDate ? await gateway.update(target.task.id, { scheduledDate: target.scheduledDate }) : null;
      if (!mounted.current || operationEpoch.current !== epoch || operationTarget !== target) return;
      if (!updated) throw new RhythmGatewayError("forbidden", "This host does not expose the requested task operation.");
      setTasks((current) => current.map((task) => task.id === updated.id ? updated : task));
      setOperationTarget(null);
    } catch (error) {
      const outcome = error?.kind;
      if (outcome === "conflict" || outcome === "uncertain") {
        setOperationError(outcome);
      } else {
        handleError(error);
      }
    } finally {
      setMutationPending(false);
    }
  };
  const createTask = async (event) => {
    event.preventDefault();
    if (!canWrite) return;
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const data = new FormData(form);
    const title = String(data.get("title") ?? "").trim();
    if (!title) {
      createTitleRef.current?.focus();
      return;
    }
    setMutationPending(true);
    try {
      const created = await gateway.create({
        title,
        notes: String(data.get("notes") ?? "").trim(),
        scheduledDate: String(data.get("scheduledDate") ?? "") || void 0,
        dueDate: String(data.get("dueDate") ?? "") || void 0
      });
      setTasks((current) => [...current, created]);
      const collaboratorId = String(data.get("collaboratorId") ?? "");
      if (collaboratorId) {
        const withCollaborator = await gateway.addCollaborator(created.id, collaboratorId);
        setTasks((current) => current.map((item) => item.id === withCollaborator.id ? withCollaborator : item));
      }
      form.reset();
      setCreateOpen(false);
    } catch (error) {
      handleError(error);
    } finally {
      setMutationPending(false);
    }
  };
  const saveInspector = async (event) => {
    event.preventDefault();
    if (!canWrite || !selectedTask) return;
    const data = new FormData(event.currentTarget);
    const title = String(data.get("title") ?? "").trim();
    if (!title) return;
    setMutationPending(true);
    try {
      const updated = await gateway.update(selectedTask.id, {
        title,
        notes: String(data.get("notes") ?? ""),
        scheduledDate: String(data.get("scheduledDate") ?? "") || void 0,
        dueDate: String(data.get("dueDate") ?? "") || void 0,
        preferredAgent: String(data.get("preferredAgent") ?? ""),
        energy: String(data.get("energy") ?? "")
      });
      setTasks((current) => current.map((task) => task.id === selectedTask.id ? updated : task));
    } catch (error) {
      handleError(error);
    } finally {
      setMutationPending(false);
    }
  };
  const addCollaborator = async (memberId) => {
    if (!canWrite || !selectedTask) return;
    try {
      const updated = await gateway.addCollaborator(selectedTask.id, memberId);
      setTasks((current) => current.map((task) => task.id === updated.id ? updated : task));
      setCollaboratorPickerOpen(false);
    } catch (error) {
      handleError(error);
    }
  };
  const removeCollaborator = async (memberId) => {
    if (!canWrite || !selectedTask) return;
    try {
      const updated = await gateway.removeCollaborator(selectedTask.id, memberId);
      setTasks((current) => current.map((task) => task.id === updated.id ? updated : task));
    } catch (error) {
      handleError(error);
    }
  };
  const confirmDelete = async () => {
    if (!canWrite || !deleteTarget) return;
    setMutationPending(true);
    try {
      await gateway.delete(deleteTarget.id);
      setTasks((current) => current.filter((task) => task.id !== deleteTarget.id));
      if (selectedId === deleteTarget.id) setSelectedId(null);
      setDeleteTarget(null);
    } catch (error) {
      handleError(error);
    } finally {
      setMutationPending(false);
    }
  };
  const moveTask = (status) => {
    if (!draggedId) return;
    const task = tasks.find((item) => item.id === draggedId);
    if (canWrite && task && task.status !== status && !isSourceReadonly(task)) void changeStatus(task, status);
    setDraggedId(null);
  };
  const launchQuickAction = (actionId, label) => {
    if (!selectedTask) return;
    host.onRequestFollowUp?.({ screen: "tasks", label, action: actionId, relatedId: selectedTask.id });
  };
  const clearFilters = () => {
    setSearch("");
    setTag("all");
    setMinimumPriority("0");
    setCompletion("open");
    setDateWindow("all");
  };
  const renderTaskRow = (task) => {
    const isOwner = !task.isShared;
    const readonly = !canWrite || isSourceReadonly(task) || mutationPending;
    return /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "task-row", role: "row", "aria-selected": selectedId === task.id, "data-status": task.status, "data-testid": `task-row-${task.id}`, children: [
      /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "task-cell complete-cell", role: "gridcell", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("label", { className: "task-complete-label", children: [
          /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "sr-only", children: [
            task.status === "done" ? "Reopen" : "Complete",
            " ",
            task.title
          ] }),
          /* @__PURE__ */ jsxRuntime.jsx(
            "input",
            {
              type: "checkbox",
              checked: task.status === "done",
              disabled: !canComplete || isSourceReadonly(task) || mutationPending,
              "aria-describedby": !canComplete || isSourceReadonly(task) ? readonlyReasonId : void 0,
              onChange: () => requestTaskOperation(task, "complete"),
              "data-testid": `task-complete-${task.id}`
            }
          )
        ] }),
        canReschedule && !isSourceReadonly(task) && /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-button", type: "button", disabled: mutationPending, onClick: () => requestTaskOperation(task, "reschedule"), "data-testid": `task-reschedule-${task.id}`, children: "Reschedule" })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "task-cell main-cell", role: "gridcell", children: /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "task-row-main", type: "button", onClick: () => openInspector(task), "data-testid": `task-select-${task.id}`, children: [
        /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "task-row-copy", children: [
          /* @__PURE__ */ jsxRuntime.jsx("span", { className: "task-kicker", children: task.sourceName ?? taskStatusLabels[task.status] }),
          /* @__PURE__ */ jsxRuntime.jsx("h3", { "data-testid": "task-title", children: task.title }),
          /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "task-meta", children: [
            dateLabel(task),
            task.priority ? ` \xB7 P${task.priority}` : ""
          ] })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsx("span", { className: "task-tags", "aria-label": task.tags.length ? `Tags: ${task.tags.join(", ")}` : "No tags", children: task.tags.slice(0, 3).map((item) => /* @__PURE__ */ jsxRuntime.jsx("span", { children: item }, item)) })
      ] }) }),
      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "task-cell inspect-cell", role: "gridcell", children: /* @__PURE__ */ jsxRuntime.jsx("button", { className: "icon-button task-inspect-button", type: "button", "aria-label": `Inspect ${task.title}`, onClick: () => openInspector(task), "data-testid": `task-inspect-${task.id}`, children: /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "chevronRight", size: 15 }) }) }),
      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "task-cell menu-cell", role: "gridcell", children: /* @__PURE__ */ jsxRuntime.jsx(TaskMenu, { task, readonly, isOwner, ownerOnlyReasonId, readonlyReasonId, onInspect: () => openInspector(task), onDelete: () => setDeleteTarget(task) }) })
    ] }, task.id);
  };
  const collaboratorCandidates = selectedTask ? members.filter((member) => member.id !== selectedTask.ownerId && !selectedTask.collaborators.some((existing) => existing.id === member.id)) : [];
  const selectedIsOwner = selectedTask ? !selectedTask.isShared : false;
  const selectedReadonly = Boolean(selectedTask && (!canWrite || isSourceReadonly(selectedTask) || mutationPending));
  return /* @__PURE__ */ jsxRuntime.jsx(ScreenRoot, { screenName: "Tasks", testId: "rhythm-tasks-screen", children: /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "page-shell pg-tasks", "aria-busy": surfaceState === "loading", children: [
    /* @__PURE__ */ jsxRuntime.jsxs("header", { className: "tasks-header", children: [
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "tasks-heading", children: [
        /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Planning queue" }),
        /* @__PURE__ */ jsxRuntime.jsx("h1", { children: "Tasks" }),
        /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Shape the next useful handoff without losing the wider rhythm." })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "tasks-header-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsxs("span", { className: "tasks-count", "data-testid": "tasks-visible-count", children: [
          visibleTasks.length,
          " ",
          visibleTasks.length === 1 ? "task" : "tasks"
        ] }),
        /* @__PURE__ */ jsxRuntime.jsx(HeaderTaskAction, { onClick: () => canWrite && setCreateOpen(true), disabled: !canWrite || !showsWorkspace || mutationPending, testId: "tasks-header-add-task" }),
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "tasks-view-switch", "aria-label": "Task presentation", children: [
          /* @__PURE__ */ jsxRuntime.jsx("button", { type: "button", "aria-pressed": view === "list", onClick: () => setView("list"), "data-testid": "tasks-view-list", children: "List" }),
          /* @__PURE__ */ jsxRuntime.jsx("button", { type: "button", "aria-pressed": view === "board", onClick: () => setView("board"), "data-testid": "tasks-view-board", children: "Board" })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "tasks-scroll", role: "region", "aria-label": "Tasks workspace content", tabIndex: 0, children: [
      !showsWorkspace && /* @__PURE__ */ jsxRuntime.jsx(StatePanel9, { state: surfaceState, onRetry: () => void load(), onEmpty: () => canWrite && setCreateOpen(true), canWrite }),
      showsWorkspace && /* @__PURE__ */ jsxRuntime.jsxs(jsxRuntime.Fragment, { children: [
        /* @__PURE__ */ jsxRuntime.jsxs("p", { className: "tasks-owner-note", id: ownerOnlyReasonId, children: [
          /* @__PURE__ */ jsxRuntime.jsx("strong", { children: "Shared-task permissions" }),
          " Collaborators may edit and complete; only the task owner can add or remove collaborators or delete."
        ] }),
        /* @__PURE__ */ jsxRuntime.jsx("p", { className: "sr-only", id: readonlyReasonId, children: "This task is synchronized from another source of truth and is inspect-only here." }),
        !canWrite && /* @__PURE__ */ jsxRuntime.jsxs("p", { className: "inspector-prerequisite", role: "status", "data-testid": "tasks-readonly-explanation", children: [
          /* @__PURE__ */ jsxRuntime.jsx("strong", { children: "Read-only workspace" }),
          /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Your host has not granted Tasks write access. You can inspect tasks and ask Hermes, but changes are unavailable." })
        ] }),
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "tasks-workspace-layout", children: [
          /* @__PURE__ */ jsxRuntime.jsx("div", { className: "tasks-collection", children: /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "tasks-workspace", "aria-labelledby": "tasks-workspace-title", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "tasks-controls", children: [
              /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntime.jsx("span", { className: "eyebrow", children: "Organize" }),
                /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "tasks-workspace-title", children: view === "list" ? "Task list" : "Task board" })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "tasks-filter-grid", children: [
                /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "search-field", children: [
                  /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "search", size: 14 }),
                  /* @__PURE__ */ jsxRuntime.jsx("label", { className: "sr-only", htmlFor: "tasks-search-input", children: "Search tasks" }),
                  /* @__PURE__ */ jsxRuntime.jsx("input", { id: "tasks-search-input", value: search, onChange: (event) => setSearch(event.target.value), placeholder: "Search tasks", "data-testid": "tasks-search" }),
                  search && /* @__PURE__ */ jsxRuntime.jsx("button", { className: "tasks-search-clear", type: "button", "aria-label": "Clear task search", onClick: () => setSearch(""), "data-testid": "tasks-clear-search", children: /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "close", size: 13 }) })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
                  /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Tag" }),
                  /* @__PURE__ */ jsxRuntime.jsxs("select", { value: tag, onChange: (event) => setTag(event.target.value), "data-testid": "tasks-tag-filter", children: [
                    /* @__PURE__ */ jsxRuntime.jsx("option", { value: "all", children: "All tags" }),
                    tagOptions.map((item) => /* @__PURE__ */ jsxRuntime.jsx("option", { value: item, children: item }, item))
                  ] })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
                  /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Priority" }),
                  /* @__PURE__ */ jsxRuntime.jsxs("select", { value: minimumPriority, onChange: (event) => setMinimumPriority(event.target.value), "data-testid": "tasks-priority-filter", children: [
                    /* @__PURE__ */ jsxRuntime.jsx("option", { value: "0", children: "Any priority" }),
                    /* @__PURE__ */ jsxRuntime.jsx("option", { value: "1", children: "P1+" }),
                    /* @__PURE__ */ jsxRuntime.jsx("option", { value: "2", children: "P2+" }),
                    /* @__PURE__ */ jsxRuntime.jsx("option", { value: "3", children: "P3+" })
                  ] })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
                  /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Open / All" }),
                  /* @__PURE__ */ jsxRuntime.jsxs("select", { value: completion, onChange: (event) => setCompletion(event.target.value), "data-testid": "tasks-completion-filter", children: [
                    /* @__PURE__ */ jsxRuntime.jsx("option", { value: "open", children: "Open" }),
                    /* @__PURE__ */ jsxRuntime.jsx("option", { value: "all", children: "All" })
                  ] })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
                  /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Date window" }),
                  /* @__PURE__ */ jsxRuntime.jsxs("select", { value: dateWindow, onChange: (event) => setDateWindow(event.target.value), "data-testid": "tasks-date-filter", children: [
                    /* @__PURE__ */ jsxRuntime.jsx("option", { value: "all", children: "All" }),
                    /* @__PURE__ */ jsxRuntime.jsx("option", { value: "today", children: "Today" }),
                    /* @__PURE__ */ jsxRuntime.jsx("option", { value: "week", children: "This Week" }),
                    /* @__PURE__ */ jsxRuntime.jsx("option", { value: "month", children: "This Month" })
                  ] })
                ] }),
                view === "list" && /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
                  /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Sort" }),
                  /* @__PURE__ */ jsxRuntime.jsxs("select", { value: sort, onChange: (event) => setSort(event.target.value), "data-testid": "tasks-sort", children: [
                    /* @__PURE__ */ jsxRuntime.jsx("option", { value: "due", children: "Due date" }),
                    /* @__PURE__ */ jsxRuntime.jsx("option", { value: "created", children: "Created date" }),
                    /* @__PURE__ */ jsxRuntime.jsx("option", { value: "status", children: "Status" }),
                    /* @__PURE__ */ jsxRuntime.jsx("option", { value: "title", children: "Title" })
                  ] })
                ] })
              ] })
            ] }),
            visibleTasks.length === 0 ? /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "tasks-no-results", "data-testid": "tasks-no-results", children: [
              /* @__PURE__ */ jsxRuntime.jsx("h2", { children: search ? "No matching tasks" : "Nothing to show" }),
              /* @__PURE__ */ jsxRuntime.jsx("p", { children: search ? "Clear the search to restore the queue." : "Clear an active filter to see the full task list." }),
              /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: clearFilters, "data-testid": "tasks-clear-filters", children: "Clear filters" })
            ] }) : view === "list" ? /* @__PURE__ */ jsxRuntime.jsx("div", { className: "tasks-list", "data-testid": "tasks-list", children: groupedTasks.map((group) => /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "task-group", "aria-labelledby": `task-group-title-${group.bucket}`, "data-testid": `task-group-${group.bucket}`, children: [
              /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
                /* @__PURE__ */ jsxRuntime.jsx("h2", { id: `task-group-title-${group.bucket}`, children: bucketLabels[group.bucket] }),
                /* @__PURE__ */ jsxRuntime.jsx("span", { children: group.tasks.length })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsx("div", { role: "grid", "aria-label": `${bucketLabels[group.bucket]} tasks`, children: group.tasks.map(renderTaskRow) })
            ] }, group.bucket)) }) : /* @__PURE__ */ jsxRuntime.jsx("div", { className: "kanban-board", role: "region", tabIndex: 0, "data-testid": "tasks-board", "aria-label": "Task status board", children: boardStatuses.map((status) => {
              const columnTasks = visibleTasks.filter((task) => task.status === status);
              return /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "kanban-column", onDragOver: (event) => event.preventDefault(), onDrop: () => moveTask(status), "aria-labelledby": `kanban-title-${status}`, "data-testid": `kanban-column-${status.replaceAll("_", "-")}`, children: [
                /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
                  /* @__PURE__ */ jsxRuntime.jsx("h2", { id: `kanban-title-${status}`, children: taskStatusLabels[status] }),
                  /* @__PURE__ */ jsxRuntime.jsx("span", { children: columnTasks.length })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsx("div", { className: "kanban-stack", role: "listbox", "aria-label": `${taskStatusLabels[status]} tasks`, children: columnTasks.length ? columnTasks.map((task) => /* @__PURE__ */ jsxRuntime.jsxs(
                  "div",
                  {
                    className: "task-card",
                    role: "option",
                    tabIndex: 0,
                    draggable: canWrite && !isSourceReadonly(task),
                    "aria-selected": selectedId === task.id,
                    "aria-label": `Inspect ${task.title}`,
                    onDragStart: () => setDraggedId(task.id),
                    onClick: () => openInspector(task),
                    onKeyDown: (event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        openInspector(task);
                      }
                    },
                    "data-testid": `task-card-${task.id}`,
                    children: [
                      /* @__PURE__ */ jsxRuntime.jsx("span", { className: "task-kicker", children: taskStatusLabels[task.status] }),
                      /* @__PURE__ */ jsxRuntime.jsx("h3", { children: task.title }),
                      /* @__PURE__ */ jsxRuntime.jsx("p", { children: dateLabel(task) }),
                      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "task-card-tags", children: [
                        task.priority ? /* @__PURE__ */ jsxRuntime.jsxs("span", { children: [
                          "P",
                          task.priority
                        ] }) : null,
                        task.tags.slice(0, 3).map((item) => /* @__PURE__ */ jsxRuntime.jsx("span", { children: item }, item))
                      ] })
                    ]
                  },
                  task.id
                )) : /* @__PURE__ */ jsxRuntime.jsx("p", { className: "kanban-empty", children: "No tasks in this stage." }) })
              ] }, status);
            }) })
          ] }) }),
          /* @__PURE__ */ jsxRuntime.jsx("aside", { className: "task-detail-column", "aria-label": "Selected task", "data-testid": "task-inspector", children: selectedTask ? /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "task-detail", "aria-labelledby": "task-detail-title", children: [
            /* @__PURE__ */ jsxRuntime.jsxs("header", { children: [
              /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                /* @__PURE__ */ jsxRuntime.jsx("span", { className: "task-detail-state", children: taskStatusLabels[selectedTask.status] }),
                /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "task-detail-title", children: selectedTask.title }),
                /* @__PURE__ */ jsxRuntime.jsxs("p", { children: [
                  selectedTask.priority ? `P${selectedTask.priority} \xB7 ` : "",
                  selectedTask.sourceName ?? "Rhythm task",
                  " \xB7 ",
                  dateLabel(selectedTask)
                ] })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsx("button", { className: "text-button", type: "button", onClick: closeInspector, "data-testid": "task-detail-close", children: "Close" })
            ] }),
            selectedReadonly && /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "inspector-prerequisite", role: "status", children: [
              /* @__PURE__ */ jsxRuntime.jsx("strong", { children: canWrite ? "Synchronized source of truth" : "Read-only workspace" }),
              /* @__PURE__ */ jsxRuntime.jsx("span", { children: canWrite ? "This task is inspect-only here." : "Your host has not granted Tasks write access." })
            ] }),
            /* @__PURE__ */ jsxRuntime.jsxs("form", { className: "task-inspector-form", onSubmit: saveInspector, children: [
              /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "task-source-grid", children: [
                /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                  /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Created by" }),
                  /* @__PURE__ */ jsxRuntime.jsx("strong", { "data-testid": "task-created-by", children: selectedTask.createdBy })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                  /* @__PURE__ */ jsxRuntime.jsx("span", { children: "Status" }),
                  /* @__PURE__ */ jsxRuntime.jsx("strong", { children: taskStatusLabels[selectedTask.status] })
                ] })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsxs("fieldset", { disabled: selectedReadonly, children: [
                /* @__PURE__ */ jsxRuntime.jsx("legend", { className: "sr-only", children: "Task details" }),
                /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
                  "Title",
                  /* @__PURE__ */ jsxRuntime.jsx("input", { disabled: selectedReadonly, name: "title", required: true, defaultValue: selectedTask.title, "data-testid": "task-edit-title" })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
                  "Notes",
                  /* @__PURE__ */ jsxRuntime.jsx("textarea", { disabled: selectedReadonly, name: "notes", rows: 4, defaultValue: selectedTask.notes, "data-testid": "task-edit-notes" })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "inspector-pair", children: [
                  /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
                    "Scheduled date",
                    /* @__PURE__ */ jsxRuntime.jsx("input", { disabled: selectedReadonly, name: "scheduledDate", type: "date", defaultValue: selectedTask.scheduledDate ?? "", "data-testid": "task-edit-scheduled-date" })
                  ] }),
                  /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
                    "Due date",
                    /* @__PURE__ */ jsxRuntime.jsx("input", { disabled: selectedReadonly, name: "dueDate", type: "date", defaultValue: selectedTask.dueDate ?? "", "data-testid": "task-edit-due-date" })
                  ] })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "inspector-pair", children: [
                  /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
                    "Default agent",
                    /* @__PURE__ */ jsxRuntime.jsxs("select", { disabled: selectedReadonly, name: "preferredAgent", defaultValue: selectedTask.preferredAgent, "data-testid": "task-edit-agent", children: [
                      /* @__PURE__ */ jsxRuntime.jsx("option", { value: "", children: "None" }),
                      /* @__PURE__ */ jsxRuntime.jsx("option", { value: "claude-code", children: "Claude Code" }),
                      /* @__PURE__ */ jsxRuntime.jsx("option", { value: "codex", children: "Codex" })
                    ] })
                  ] }),
                  /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
                    "Energy",
                    /* @__PURE__ */ jsxRuntime.jsxs("select", { disabled: selectedReadonly, name: "energy", defaultValue: selectedTask.energy, "data-testid": "task-edit-energy", children: [
                      /* @__PURE__ */ jsxRuntime.jsx("option", { value: "", children: "None" }),
                      /* @__PURE__ */ jsxRuntime.jsx("option", { value: "\u{1F525}", children: "\u{1F525} Fire" }),
                      /* @__PURE__ */ jsxRuntime.jsx("option", { value: "\u26A1", children: "\u26A1 Electric" }),
                      /* @__PURE__ */ jsxRuntime.jsx("option", { value: "\u{1F331}", children: "\u{1F331} Grounded" })
                    ] })
                  ] })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsxs("footer", { className: "task-detail-form-actions", children: [
                  /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", disabled: selectedReadonly, onClick: () => void changeStatus(selectedTask, selectedTask.status === "done" ? "open" : "done"), "data-testid": "task-detail-complete", children: selectedTask.status === "done" ? "Reopen" : "Complete" }),
                  /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "submit", disabled: selectedReadonly, "data-testid": "task-save", children: "Save changes" })
                ] })
              ] })
            ] }, selectedTask.id),
            /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "task-people", "aria-labelledby": "task-people-title", children: [
              /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "inspector-section-heading", children: [
                /* @__PURE__ */ jsxRuntime.jsxs("div", { children: [
                  /* @__PURE__ */ jsxRuntime.jsx("h3", { id: "task-people-title", children: "People" }),
                  /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Collaborators on this task." })
                ] }),
                /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "secondary-button", type: "button", disabled: !selectedIsOwner || selectedReadonly, "aria-describedby": !selectedIsOwner ? ownerOnlyReasonId : selectedReadonly ? readonlyReasonId : void 0, onClick: () => setCollaboratorPickerOpen(true), "data-testid": "task-add-collaborator", children: [
                  /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "plus", size: 14 }),
                  "Add"
                ] })
              ] }),
              /* @__PURE__ */ jsxRuntime.jsx("div", { className: "collaborator-list", children: selectedTask.collaborators.length ? selectedTask.collaborators.map((person) => /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "collaborator-chip", "data-testid": `task-collaborator-${person.id}`, children: [
                /* @__PURE__ */ jsxRuntime.jsx("span", { "aria-hidden": "true", children: person.initials }),
                /* @__PURE__ */ jsxRuntime.jsx("strong", { children: person.name }),
                /* @__PURE__ */ jsxRuntime.jsx("button", { className: "icon-button", type: "button", disabled: !selectedIsOwner || selectedReadonly, "aria-label": `Remove ${person.name}`, onClick: () => void removeCollaborator(person.id), "data-testid": `task-remove-collaborator-${person.id}`, children: /* @__PURE__ */ jsxRuntime.jsx(Icon, { name: "close", size: 13 }) })
              ] }, person.id)) : /* @__PURE__ */ jsxRuntime.jsx("p", { children: "No collaborators yet." }) })
            ] }),
            (!selectedReadonly || !canWrite) && /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "task-quick-actions", "aria-labelledby": "task-quick-title", children: [
              /* @__PURE__ */ jsxRuntime.jsx("h3", { id: "task-quick-title", children: "Quick actions" }),
              /* @__PURE__ */ jsxRuntime.jsx("div", { children: quickActionPresets.map((action) => /* @__PURE__ */ jsxRuntime.jsx("button", { className: "task-action-chip", type: "button", onClick: () => launchQuickAction(action.id, action.label), "data-testid": `quick-action-${action.id}`, children: action.label }, action.id)) })
            ] })
          ] }) : /* @__PURE__ */ jsxRuntime.jsxs("section", { className: "task-detail-empty", "aria-labelledby": "task-detail-empty-title", children: [
            /* @__PURE__ */ jsxRuntime.jsx("h2", { id: "task-detail-empty-title", children: "Select a task" }),
            /* @__PURE__ */ jsxRuntime.jsx("p", { children: "Open a task to review its context, people, and next actions without leaving the queue." })
          ] }) })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: createOpen, onClose: () => setCreateOpen(false), title: "Add task", description: "Set the task details now. More people are available after creation.", testId: "task-create-dialog", children: /* @__PURE__ */ jsxRuntime.jsx(
      TaskCreateForm,
      {
        idPrefix: "tasks-create",
        onSubmit: createTask,
        onCancel: () => setCreateOpen(false),
        members: members.filter((member) => member.id !== currentUserId),
        titleRef: createTitleRef,
        disabled: !canWrite || mutationPending,
        testIds: { title: "task-create-title", notes: "task-create-notes", scheduledDate: "task-create-scheduled-date", dueDate: "task-create-due-date", collaborator: "task-create-collaborator", cancel: "task-create-cancel", submit: "task-create-submit", mutations: "tasks-mutations" }
      }
    ) }),
    /* @__PURE__ */ jsxRuntime.jsx(FocusDialog, { open: collaboratorPickerOpen, onClose: () => setCollaboratorPickerOpen(false), title: "Add collaborator", description: "Only workspace members who are not the owner or already collaborating are shown.", testId: "task-collaborator-picker", children: /* @__PURE__ */ jsxRuntime.jsx("div", { className: "collaborator-options", role: "listbox", "aria-label": "Available collaborators", children: collaboratorCandidates.length ? collaboratorCandidates.map((person) => /* @__PURE__ */ jsxRuntime.jsxs("button", { className: "secondary-button", role: "option", "aria-selected": "false", type: "button", onClick: () => void addCollaborator(person.id), "data-testid": `task-collaborator-option-${person.id}`, children: [
      /* @__PURE__ */ jsxRuntime.jsx("span", { children: person.initials }),
      /* @__PURE__ */ jsxRuntime.jsx("strong", { children: person.name })
    ] }, person.id)) : /* @__PURE__ */ jsxRuntime.jsx("p", { children: "No eligible collaborators remain." }) }) }),
    /* @__PURE__ */ jsxRuntime.jsxs(FocusDialog, { open: Boolean(deleteTarget), onClose: () => setDeleteTarget(null), title: deleteTarget ? `Delete "${deleteTarget.title}"?` : "Delete task?", description: "This cannot be undone.", testId: "task-delete-dialog", children: [
      /* @__PURE__ */ jsxRuntime.jsx("p", { className: "delete-copy", children: "The task and its collaborator links will be removed." }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => setDeleteTarget(null), "data-testid": "task-delete-cancel", children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "danger-button", type: "button", disabled: !canWrite || mutationPending, onClick: () => void confirmDelete(), "data-testid": "task-delete-confirm", children: "Delete task" })
      ] })
    ] }),
    /* @__PURE__ */ jsxRuntime.jsxs(FocusDialog, { open: Boolean(operationTarget), onClose: () => {
      operationEpoch.current += 1;
      setOperationError(null);
      setOperationTarget(null);
    }, title: operationTarget?.operation === "complete" ? `Complete \u201C${operationTarget.task.title}\u201D?` : `Reschedule \u201C${operationTarget?.task.title ?? ""}\u201D?`, description: "This action is sent only after you confirm it.", testId: "task-operation-confirmation", children: [
      operationTarget?.operation === "reschedule" && /* @__PURE__ */ jsxRuntime.jsxs("label", { children: [
        "Scheduled date",
        /* @__PURE__ */ jsxRuntime.jsx("input", { type: "date", value: operationTarget.scheduledDate ?? "", disabled: mutationPending, onChange: (event) => setOperationTarget((current) => current ? { ...current, scheduledDate: event.target.value } : current), "data-testid": "task-operation-date" })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsx("p", { role: "status", children: operationTarget?.operation === "complete" ? "Mark this task complete." : `Set the scheduled date to ${operationTarget?.scheduledDate ?? ""}.` }),
      operationError && /* @__PURE__ */ jsxRuntime.jsxs("div", { role: "alert", "data-testid": "task-operation-outcome", children: [
        /* @__PURE__ */ jsxRuntime.jsx("p", { children: operationError === "conflict" ? "This task changed elsewhere. Reload before retrying." : "We could not verify whether the task operation was applied. Reload before retrying." }),
        /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => void reloadTaskOperationContext(), "data-testid": "task-operation-reload", children: "Reload" }),
          /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: retryTaskOperation, "data-testid": "task-operation-retry", children: "Retry" })
        ] })
      ] }),
      /* @__PURE__ */ jsxRuntime.jsxs("div", { className: "dialog-actions", children: [
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "secondary-button", type: "button", onClick: () => {
          operationEpoch.current += 1;
          setOperationError(null);
          setOperationTarget(null);
        }, children: "Cancel" }),
        /* @__PURE__ */ jsxRuntime.jsx("button", { className: "primary-button", type: "button", disabled: mutationPending || operationTarget?.operation === "reschedule" && !isIsoCalendarDate(operationTarget.scheduledDate), onClick: () => void confirmTaskOperation(), "data-autofocus": true, "data-testid": "task-operation-confirm", children: "Confirm" })
      ] })
    ] })
  ] }) });
}

exports.ArtifactsScreen = ArtifactsScreen;
exports.AutomationsScreen = AutomationsScreen;
exports.DashboardScreen = DashboardScreen;
exports.FacilitiesScreen = FacilitiesScreen;
exports.FocusDialog = FocusDialog;
exports.HeaderTaskAction = HeaderTaskAction;
exports.Icon = Icon;
exports.IntegrationsScreen = IntegrationsScreen;
exports.MessagesScreen = MessagesScreen;
exports.PlannerScreen = PlannerScreen;
exports.ProjectsScreen = ProjectsScreen;
exports.RHYTHM_ROOT_CLASS = RHYTHM_ROOT_CLASS;
exports.RhythmGatewayError = RhythmGatewayError;
exports.RhythmWorkspaceProvider = RhythmWorkspaceProvider;
exports.RhythmsScreen = RhythmsScreen;
exports.TaskCreateForm = TaskCreateForm;
exports.TasksScreen = TasksScreen;
exports.defaultRhythmTokens = defaultRhythmTokens;
exports.mapHostTokens = mapHostTokens;
exports.quickActionPresets = quickActionPresets;
exports.useRhythmDomainGateway = useRhythmDomainGateway;
exports.useRhythmHost = useRhythmHost;
//# sourceMappingURL=index.cjs.map
//# sourceMappingURL=index.cjs.map