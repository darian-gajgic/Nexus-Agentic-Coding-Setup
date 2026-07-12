# Bench-02 Answer Sheet — how to answer each arm's questions

You play the same client in all three sessions. Which questions a system asks (and whether it asks at all) is part of what we measure — so the INFORMATION each arm can get must be identical, and only obtainable by asking.

## Rules (binding)

1. Answer ONLY what is asked. Never volunteer sheet content an arm didn't ask about.
2. Use the canonical answers below word-for-word where they fit; keep improvised answers to one short sentence.
3. If a question isn't covered below, answer: `You decide — whatever a typical customer would want.` and log it as "off-sheet".
4. Log EVERY question and your answer in RESULTS.md under the arm's Q&A log (also the skippable/optional ones).
5. In Nexus, answer skippable interview questions instead of skipping them (comparability).
6. Respond promptly — wall-clock includes your thinking time, equally for all arms.

## Canonical answers

| If asked about… | Answer |
|---|---|
| Tech stack / framework / language | "Your choice — it just has to run locally on Linux; Python and Node are both installed." |
| Which AI models the helper must know | "Popular open models people run at home: Llama 3 family (8B–70B), Mistral/Mixtral, Qwen 2.5 (7B–72B), DeepSeek R1 distills, plus image generation (Stable Diffusion XL, Flux). From small starter setups up to multi-GPU." |
| Budget handling in the helper | "The customer can enter an optional budget; without one, show a sensible mid-range and a high-end option." |
| Currency / region | "Euros, German market." |
| Shop name / branding / look | "Pick something fitting. Clean modern look, dark theme is fine." |
| Catalog categories / scope | "GPUs, CPUs, motherboards, RAM, PSUs, storage, cooling, cases. A few accessories are fine too." |
| How many products | "A broad spectrum — enough that recommendations have real choices, 40+ overall." |
| PowerPoint content | "Step-by-step: hardware assembly plus software setup (OS, drivers, a runtime like Ollama) for the exact recommended parts." |
| PPTX static or per-recommendation | "Generated for the customer's specific recommendation." |
| Live internet from the app | "It must work offline on my machine — bake researched knowledge in during development." |
| Hosting / deployment | "Local only. One command to start is ideal." |
| Users / accounts / payment / admin | "Not needed — demo only. A cart that pretends to check out is enough." |
| Database or files | "Your choice." |
| Timeline / priorities | "Get the full flow working end to end first, polish second." |

## Test personas for the finished shops (Phase E — use verbatim, same for every arm)

- **P1:** `I want to run Llama 3 70B locally for coding help.`
- **P2:** `I want a cheap starter setup for 7B-8B models, budget 1200 euros.`
- **P3:** `I want to generate images with Flux and also run a 13B chat model.`

Sanity flags (any of these = persona check fails):
- P1 recommended with a single 16GB-or-smaller GPU, or total VRAM < 40GB without the shop saying it's a compromise/quantized setup.
- Any build whose PSU wattage is obviously below the recommended GPU+CPU needs.
- CPU and motherboard with incompatible sockets, or RAM type the board doesn't support.
- P2 grossly over budget (> ~1450 €) with no cheaper alternative offered.
- Shopping list missing whole categories needed for a working machine (no PSU, no RAM, …).
