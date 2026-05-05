# Design Guidelines - RAG Chatbot

> Living document. Last updated: 2026-04-30.

## Design Philosophy

**Clean, minimal, content-focused.** Enterprise-grade but not boring. Dark mode default. Source citations prominent but not distracting. Chat interface feels natural and responsive.

Style direction: **AI-Native UI + Trust & Authority** with subtle glassmorphism accents.

---

## 1. Color System

### 1.1 Dark Mode (Default)

| Token | Hex | Usage |
|-------|-----|-------|
| `--bg-primary` | `#0B0F1A` | App background |
| `--bg-secondary` | `#111827` | Sidebar, panels |
| `--bg-tertiary` | `#1F2937` | Cards, elevated surfaces |
| `--bg-input` | `#1A2332` | Input fields, text areas |
| `--bg-hover` | `#263044` | Hover states |
| `--border-primary` | `#1E293B` | Default borders |
| `--border-secondary` | `#334155` | Emphasized borders |
| `--text-primary` | `#F1F5F9` | Headings, primary text |
| `--text-secondary` | `#94A3B8` | Body text, descriptions |
| `--text-tertiary` | `#64748B` | Placeholders, muted text |
| `--text-inverse` | `#0F172A` | Text on light backgrounds |

### 1.2 Light Mode

| Token | Hex | Usage |
|-------|-----|-------|
| `--bg-primary` | `#FAFBFC` | App background |
| `--bg-secondary` | `#FFFFFF` | Sidebar, panels |
| `--bg-tertiary` | `#F1F5F9` | Cards, elevated surfaces |
| `--bg-input` | `#FFFFFF` | Input fields |
| `--bg-hover` | `#E2E8F0` | Hover states |
| `--border-primary` | `#E2E8F0` | Default borders |
| `--border-secondary` | `#CBD5E1` | Emphasized borders |
| `--text-primary` | `#0F172A` | Headings, primary text |
| `--text-secondary` | `#475569` | Body text, descriptions |
| `--text-tertiary` | `#94A3B8` | Placeholders, muted text |

### 1.3 Accent Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `--accent-primary` | `#6366F1` | Primary actions, AI indicators, links |
| `--accent-primary-hover` | `#818CF8` | Primary hover |
| `--accent-primary-muted` | `#6366F11A` | Subtle backgrounds (10% opacity) |
| `--accent-secondary` | `#8B5CF6` | Secondary AI elements, gradients |
| `--accent-success` | `#10B981` | Success, indexed status, online |
| `--accent-warning` | `#F59E0B` | Processing, pending states |
| `--accent-error` | `#EF4444` | Errors, failed status, destructive |
| `--accent-info` | `#3B82F6` | Info badges, tooltips |
| `--accent-citation` | `#14B8A6` | Source citations, references |

### 1.4 AI Gradient

```css
--gradient-ai: linear-gradient(135deg, #6366F1 0%, #8B5CF6 50%, #A78BFA 100%);
--gradient-ai-subtle: linear-gradient(135deg, #6366F10D 0%, #8B5CF60D 100%);
```

Used for: AI response indicators, thinking animation, brand accents.

### 1.5 Chat Bubble Colors

| Element | Dark Mode | Light Mode |
|---------|-----------|------------|
| User message bg | `#6366F1` | `#6366F1` |
| User message text | `#FFFFFF` | `#FFFFFF` |
| AI message bg | `#1F2937` | `#F1F5F9` |
| AI message text | `#F1F5F9` | `#1E293B` |
| Citation badge bg | `#14B8A61A` | `#14B8A61A` |
| Citation badge text | `#14B8A6` | `#0D9488` |

---

## 2. Typography

### 2.1 Font Selection

**Heading:** `Plus Jakarta Sans` (Google Fonts)
- Geometric, modern, distinctive character
- Full Vietnamese support (ă, â, đ, ê, ô, ơ, ư)
- Weights: 500 (medium), 600 (semibold), 700 (bold)

**Body:** `Source Sans 3` (Google Fonts)
- Humanist sans-serif, excellent readability at small sizes
- Full Vietnamese support
- Weights: 300 (light), 400 (regular), 500 (medium), 600 (semibold)

**Monospace:** `JetBrains Mono` (Google Fonts)
- Code blocks, technical data, chunk IDs
- Weights: 400 (regular), 500 (medium)

### 2.2 Google Fonts Import

```css
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700&family=Source+Sans+3:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
```

### 2.3 Tailwind Config

```js
fontFamily: {
  heading: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
  body: ['"Source Sans 3"', 'system-ui', 'sans-serif'],
  mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
}
```

### 2.4 Type Scale (Based on 1.25 Major Third)

| Token | Size | Line Height | Weight | Usage |
|-------|------|-------------|--------|-------|
| `display-lg` | 36px / 2.25rem | 1.2 | 700 | Hero headings |
| `display-sm` | 30px / 1.875rem | 1.25 | 700 | Page titles |
| `heading-lg` | 24px / 1.5rem | 1.3 | 600 | Section headings |
| `heading-md` | 20px / 1.25rem | 1.35 | 600 | Card titles |
| `heading-sm` | 16px / 1rem | 1.4 | 600 | Subsection headings |
| `body-lg` | 16px / 1rem | 1.6 | 400 | Chat messages, primary body |
| `body-md` | 14px / 0.875rem | 1.5 | 400 | Default body, UI text |
| `body-sm` | 13px / 0.8125rem | 1.5 | 400 | Secondary text |
| `caption` | 12px / 0.75rem | 1.4 | 500 | Labels, badges, timestamps |
| `overline` | 11px / 0.6875rem | 1.4 | 600 | Overlines, uppercase labels |
| `code` | 13px / 0.8125rem | 1.6 | 400 | Code blocks, technical data |

---

## 3. Spacing System (4px Grid)

| Token | Value | Usage |
|-------|-------|-------|
| `--space-0` | 0px | Reset |
| `--space-1` | 4px | Tight gaps, icon padding |
| `--space-2` | 8px | Input padding, small gaps |
| `--space-3` | 12px | Button padding, compact spacing |
| `--space-4` | 16px | Default gap, card padding (compact) |
| `--space-5` | 20px | Medium spacing |
| `--space-6` | 24px | Card padding, section gap |
| `--space-8` | 32px | Section spacing |
| `--space-10` | 40px | Large section spacing |
| `--space-12` | 48px | Page padding |
| `--space-16` | 64px | Major section breaks |

### Layout Spacing

| Element | Value |
|---------|-------|
| Sidebar width | 280px (collapsed: 64px) |
| Chat max-width | 768px (centered) |
| Admin content max-width | 1280px |
| Page horizontal padding | 24px (mobile: 16px) |
| Card padding | 24px (mobile: 16px) |
| Card gap | 16px |
| Chat message gap | 16px |
| Input height | 44px (min touch target) |

---

## 4. Component Patterns

### 4.1 Buttons

```
Primary:    bg: accent-primary, text: white, hover: accent-primary-hover
            rounded-lg, px-4, py-2.5, font-medium, text-sm
            transition: all 150ms ease

Secondary:  bg: transparent, border: border-secondary, text: text-primary
            hover: bg-hover

Ghost:      bg: transparent, text: text-secondary
            hover: bg-hover, text: text-primary

Danger:     bg: accent-error, text: white
            hover: brightness(1.1)

Icon-only:  w-9, h-9, rounded-lg, flex items-center justify-center
            min touch: 44x44px on mobile
```

### 4.2 Input Fields

```
Default:    bg: bg-input, border: border-primary, text: text-primary
            rounded-lg, px-3, h-11, text-sm
            placeholder: text-tertiary
            focus: border-accent-primary, ring-2 ring-accent-primary/20
            transition: border-color 150ms, box-shadow 150ms

Chat Input: bg: bg-tertiary, border: border-primary
            rounded-2xl, px-4, py-3, min-h-[52px]
            auto-resize textarea (max 200px height)
            Send button inside, right-aligned
            File attachment button, left-aligned
```

### 4.3 Cards

```
Default:    bg: bg-tertiary, border: border-primary
            rounded-xl, p-6
            hover: border-border-secondary (if clickable)
            transition: border-color 200ms

Stat Card:  Same as default + overline label + large number + trend indicator
            Icon in top-right with muted accent bg

Document:   Horizontal layout on desktop, stack on mobile
            Status badge (indexed/processing/failed) in top-right
            Metadata row: chunks, date, size
```

### 4.4 Chat Bubbles

```
User:       bg: accent-primary, text: white
            rounded-2xl rounded-br-md
            max-width: 80%, align: right
            px-4, py-3

AI:         bg: bg-tertiary, text: text-primary
            rounded-2xl rounded-bl-md
            max-width: 85%, align: left
            px-4, py-3
            Avatar icon (AI logo) to the left

Citation:   Inline badge within AI message
            bg: citation/10%, text: accent-citation
            rounded-md, px-2, py-0.5, text-xs, font-medium
            Hover: bg-citation/20%, cursor-pointer
            Click: expand source panel or tooltip
```

### 4.5 Badges / Status

```
Indexed:    bg: success/10%, text: accent-success, dot indicator
Processing: bg: warning/10%, text: accent-warning, animated pulse dot
Failed:     bg: error/10%, text: accent-error, dot indicator
Draft:      bg: bg-hover, text: text-tertiary
```

### 4.6 Sidebar

```
Width:      280px (desktop), full overlay (mobile)
Background: bg-secondary
Border:     border-right: border-primary
Items:      px-3, py-2.5, rounded-lg, text-sm
Active:     bg: accent-primary/10%, text: accent-primary, font-medium
Hover:      bg: bg-hover
Sections:   overline text labels, uppercase, text-tertiary
```

### 4.7 Modal / Dialog

```
Overlay:    bg: black/60%, backdrop-blur-sm
Container:  bg: bg-secondary, border: border-primary
            rounded-2xl, p-6, max-w-lg
            shadow-2xl
            Enter: scale(0.95) → scale(1), opacity 0 → 1, 200ms ease-out
            Exit:  reverse, 150ms ease-in
```

### 4.8 Tables (Admin)

```
Header:     bg: bg-secondary, text: text-tertiary, text-xs uppercase
            sticky top, border-bottom
Row:        border-bottom: border-primary, py-3, px-4
            hover: bg-hover
            transition: background-color 150ms
Pagination: Bottom, centered, compact style
```

### 4.9 Auth Pages

```
Layout:   Two-panel shell on lg+ screens, stacked on mobile
Hero:     Dark-first background with radial gradients, subtle grid overlay,
          trust cues, and compact stat chips
Panel:    Elevated auth card with OAuth buttons, credential form, and footer link
Inputs:   Rounded-2xl, full width, clear labels, visible focus rings, password toggle
Buttons:  Gradient primary CTA, muted social buttons, hover lift, 44x44px minimum touch target
States:   Inline status/error banners for register and session-expired flows
Copy:     Keep login/register intent explicit; avoid generic "continue" wording
Classes:  `auth-screen`, `auth-shell`, `auth-hero-panel`, `auth-card`,
          `auth-input`, `auth-button-primary`, `auth-button-social`, `auth-stat-chip`
```

---

## 5. Dark Mode Strategy

### Implementation Approach

Use CSS custom properties with `data-theme` attribute on `<html>`.

```css
:root, [data-theme="dark"] {
  /* dark mode tokens (default) */
}
[data-theme="light"] {
  /* light mode overrides */
}
```

**Tailwind CSS v4:** Use `@theme` for token definitions. Apply `dark:` variant classes where needed, with dark as default via `darkMode: 'class'` or `data-theme`.

### Rules
- Dark mode is **default** -- respect system preference via `prefers-color-scheme`
- Store user preference in `localStorage` and cookie (SSR hydration)
- All colors MUST use design tokens, never raw hex in components
- Test both modes for every component
- Minimum contrast: 4.5:1 (AA) for text, 3:1 for large text and UI elements
- Shadows use opacity-based colors (not fixed grays)

---

## 6. Responsive Breakpoints

| Breakpoint | Width | Target |
|------------|-------|--------|
| `xs` | 0-479px | Small phones |
| `sm` | 480-639px | Large phones |
| `md` | 640-767px | Small tablets |
| `lg` | 768-1023px | Tablets, small laptops |
| `xl` | 1024-1279px | Laptops |
| `2xl` | 1280px+ | Desktops |

### Layout Adaptations

| Component | Mobile (<768) | Tablet (768-1023) | Desktop (1024+) |
|-----------|---------------|-------------------|-----------------|
| Sidebar | Hidden, hamburger toggle, overlay | Collapsed (icons only, 64px) | Full (280px) |
| Chat area | Full width, 16px padding | Centered, 24px padding | Centered, max-w-3xl |
| Admin grid | 1 column | 2 columns | 3-4 columns |
| Navigation | Bottom bar | Side collapsed | Side full |
| Sources panel | Bottom sheet | Side panel (slide-in) | Side panel (persistent) |
| Document cards | Stack, full width | 2-column grid | 3-column grid |

---

## 7. Animation & Transition Guidelines

### Principles
- **Purposeful:** Every animation communicates state change or provides feedback
- **Subtle:** Professional, not playful. No bounce, no overshoot
- **Fast:** Most transitions under 200ms. Nothing over 400ms
- **Accessible:** Respect `prefers-reduced-motion: reduce`

### Timing Functions
```css
--ease-default: cubic-bezier(0.4, 0, 0.2, 1);   /* general transitions */
--ease-in:      cubic-bezier(0.4, 0, 1, 1);       /* exits */
--ease-out:     cubic-bezier(0, 0, 0.2, 1);       /* entrances */
--ease-spring:  cubic-bezier(0.34, 1.56, 0.64, 1); /* interactive feedback */
```

### Duration Tokens
```css
--duration-fast:   100ms;  /* hover color, opacity */
--duration-normal: 200ms;  /* most transitions */
--duration-slow:   300ms;  /* panel slide, modal */
--duration-slower: 400ms;  /* page transitions */
```

### Specific Animations

| Element | Animation | Duration | Easing |
|---------|-----------|----------|--------|
| Button hover | background-color, transform scale(1.02) | 150ms | ease-default |
| Sidebar toggle | width, opacity | 300ms | ease-out |
| Chat message appear | translateY(8px) + opacity | 200ms | ease-out |
| AI thinking dots | 3 dots pulse, staggered 200ms | 1.4s loop | ease-in-out |
| Citation expand | max-height + opacity | 250ms | ease-out |
| Modal open | scale(0.95→1) + opacity | 200ms | ease-out |
| Toast notification | translateY(-100%) → 0 | 300ms | ease-spring |
| Skeleton loading | shimmer gradient sweep | 1.5s loop | linear |
| Status dot pulse | scale(1→1.5) + opacity | 1.5s loop | ease-in-out |
| Page transition | opacity fade | 200ms | ease-default |

### Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## 8. Accessibility Requirements (WCAG 2.1 AA)

### Color Contrast
- Normal text (< 18px): minimum **4.5:1** contrast ratio
- Large text (>= 18px bold or >= 24px): minimum **3:1**
- UI components and graphical objects: minimum **3:1**
- All accent colors verified against both dark and light backgrounds

### Keyboard Navigation
- All interactive elements focusable via Tab
- Visible focus ring: `outline: 2px solid var(--accent-primary); outline-offset: 2px;`
- Skip-to-content link on every page
- Chat input accessible via keyboard shortcut (`/` or `Ctrl+K`)
- Escape closes modals, panels, popovers

### Screen Reader Support
- Semantic HTML (nav, main, aside, article, section)
- ARIA labels on icon-only buttons
- ARIA live regions for: chat messages, loading states, toast notifications
- `role="log"` on chat message container
- `aria-busy="true"` on AI thinking state
- Document status changes announced via `aria-live="polite"`

### Form Accessibility
- All inputs have visible labels (not just placeholder)
- Error messages linked via `aria-describedby`
- Required fields marked with `aria-required`
- File upload includes accessible drag-and-drop alternative

### Motion & Visual
- Respect `prefers-reduced-motion`
- No content conveyed solely through color (use icons + text)
- Minimum touch target: 44x44px
- No auto-playing animations that can't be paused

---

## 9. Iconography

**Library:** Lucide React (consistent with shadcn/ui)

| Context | Icons |
|---------|-------|
| Chat | `MessageSquare`, `Send`, `Paperclip`, `Bot`, `User` |
| Documents | `FileText`, `Upload`, `Trash2`, `RefreshCw`, `Download` |
| Status | `CheckCircle2`, `Clock`, `AlertCircle`, `XCircle` |
| Navigation | `Menu`, `X`, `ChevronDown`, `ChevronRight`, `Search` |
| Admin | `Settings`, `Users`, `Database`, `BarChart3`, `Shield` |

Icon size: 16px (inline), 20px (buttons), 24px (navigation), 32px (empty states).

---

## 10. Shadows & Elevation

| Level | Value | Usage |
|-------|-------|-------|
| `shadow-sm` | `0 1px 2px rgba(0,0,0,0.3)` | Subtle lift (cards in dark) |
| `shadow-md` | `0 4px 6px -1px rgba(0,0,0,0.3)` | Dropdowns, popovers |
| `shadow-lg` | `0 10px 15px -3px rgba(0,0,0,0.4)` | Modals, floating panels |
| `shadow-glow` | `0 0 20px rgba(99,102,241,0.15)` | AI-related emphasis |

Note: In light mode, reduce opacity values by ~50%.

---

## 11. Z-Index Scale

| Token | Value | Usage |
|-------|-------|-------|
| `z-base` | 0 | Default content |
| `z-raised` | 10 | Sticky headers, raised cards |
| `z-dropdown` | 20 | Dropdowns, popovers |
| `z-sidebar` | 30 | Sidebar overlay (mobile) |
| `z-modal` | 40 | Modals, dialogs |
| `z-toast` | 50 | Toast notifications |
| `z-tooltip` | 60 | Tooltips |

---

## 12. File & Component Naming

```
components/
├── chat/
│   ├── chat-message-bubble.tsx
│   ├── chat-input-area.tsx
│   ├── chat-sidebar-history.tsx
│   ├── chat-source-citation.tsx
│   ├── chat-thinking-indicator.tsx
│   └── chat-sources-panel.tsx
├── admin/
│   ├── admin-document-list.tsx
│   ├── admin-upload-area.tsx
│   ├── admin-stats-card.tsx
│   ├── admin-ingestion-status.tsx
│   └── admin-document-detail-panel.tsx
├── auth/
│   ├── login-form.tsx
│   └── oauth-buttons.tsx
└── shared/
    ├── sidebar-navigation.tsx
    ├── status-badge.tsx
    ├── skeleton-loader.tsx
    └── theme-toggle.tsx
```

---

## 13. Design Tokens (CSS Custom Properties)

```css
:root {
  /* Typography */
  --font-heading: 'Plus Jakarta Sans', system-ui, sans-serif;
  --font-body: 'Source Sans 3', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, monospace;

  /* Border Radius */
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-2xl: 20px;
  --radius-full: 9999px;

  /* Transitions */
  --transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-normal: 200ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-slow: 300ms cubic-bezier(0.4, 0, 0.2, 1);
}
```
