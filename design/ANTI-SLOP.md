# Anti-slop rules for new UI and copy

Written before the v1.2 UI work, from a survey of current writing on how
AI-generated interfaces and prose give themselves away. The point is not to
redesign anything; the app's design language is already set (see
`web/styles.css` and `design/reference-mockup.html`). The point is that every
*new* element added from here on has to look like it belongs to that language
rather than to a model's statistical default.

## Visual tells to avoid

The most-cited catalogue is Adrian Krebs' audit of 1,590 Show HN landing pages,
which found 22% carried four or more of these patterns:

- Emoji used as interface icons (✨ 🚀 🎯 ⚡ 🔥 💡) in headings, buttons or list
  items. This app uses hand-written inline SVG in the `I` icon map; new icons go
  there and are drawn in the same 24×24 stroke style.
- A new gradient. The app has exactly one, on the 42px brand mark. Cards, badges
  and buttons are flat surfaces with a 1px border.
- Coloured left or top borders on cards as decoration.
- A badge floated above a heading.
- Identical feature cards in a row of three or six, each icon-heading-two-lines.
- Numbered "1, 2, 3" step sequences as a layout device.
- Stat banner rows.
- Large coloured glows and outsized box-shadows. The app has two shadow tokens,
  `--shadow-sm` and `--shadow-md`; there is no third.
- All-caps labels sprinkled freely. This app *does* use uppercase, but only at
  one size and role: the 12px `--text-faint` section label
  (`.about-section-label`, `.browse-head`). Reuse that class; don't invent new
  uppercase treatments.
- Permanent dark mode. Both themes are first-class here and every new token must
  be defined in both `:root` and `:root[data-theme="dark"]`.
- Pure `#fff` / `#000` text. The palette's ink is `#151a23` and `#e8ecf3`.
- Body text that only just clears contrast minimums.

Two tells are unavoidable-by-inheritance and stay as they are: the app is set in
Inter, and the brand mark is a purple-to-blue gradient. Both predate this work
and are part of the established identity. Changing them to dodge a checklist
would be the actual mistake.

## Language tells to avoid

- The negative parallel: "It's not just a dashboard, it's a control room."
- Vocabulary that reads as machine-default: delve, elevate, seamless(ly),
  unlock, empower, robust, leverage, "in today's fast-paced world", "at a
  glance" as filler.
- Em dashes, at any rate at all. House rule: no em dash appears in anything a
  user reads, which covers the app's own text, the README, the guide, the store
  listing and the release notes. Use a colon to introduce, a semicolon or a full
  stop to join, brackets for a true aside. Code comments and docstrings are not
  user-facing and are exempt.
- Rule-of-three lists where two items would do.
- Enthusiasm the situation doesn't earn: exclamation marks, "Great news!",
  "You're all set!", urgency around updates.
- Hedged non-answers where a plain limitation belongs.

## The voice this app already has

Short, declarative, and specific about what it cannot do. Existing examples to
match:

> Viewing service logs isn't available in the sandboxed Flatpak version of
> (Local) AI Hub. The sandbox can't read the host's systemd journal.

> Local-only · No accounts · No telemetry · Nothing phones home

> ComfyUI isn't installed on this machine

Note what these do: name the limitation, name the cause, and where possible give
the user the real alternative. No apology, no reassurance, no upsell. New copy in this update, meaning the Hermes
layer and the version check, is written to that standard.

Sources consulted: Developers Digest' write-up of the 16-pattern audit, 925
Studios and SmoothUI on generic AI UI output, PR Daily and Hunting the Muse on
prose tells.
