// Checks a model-written briefing against the figures it was given, and rejects it if it
// states a number that cannot be traced back to one.
//
// The prompt tells the model not to invent figures. That is a request, not a guarantee, and
// during development this model broke it: handed 60 proposals and 59 refusals it wrote that
// the refusals were "the remaining" of the proposals, which implies 58. Every individual
// number was real; the relationship was invented. A rule the model is asked to follow is
// worth something, but a rule the server enforces is worth more — and on a page whose entire
// claim is that a deterministic layer decides what a model is allowed to do, an unverified
// paragraph of model prose would be the one place that claim does not hold.
//
// So this is the same shape as the risk gate: the model proposes, something deterministic
// disposes. It fails closed. A briefing that cannot be verified is not shown at all.

const WORD_NUMBERS: Record<string, number> = {
  zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8,
  nine: 9, ten: 10, eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15,
  sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19, twenty: 20, thirty: 30,
  forty: 40, fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90, hundred: 100,
  thousand: 1000,
};

// Numbers are not the only way to state something untrue. Two models, independently, have
// now written that the refusals were "the remaining" of the proposals — 60 proposals, 2
// approved, "the remaining 59 refused". Every figure in that sentence is real and the digit
// scan passes it happily; the invented part is the relationship, which implies 58 and is
// wrong because gate verdicts and proposals are different populations. So subtraction
// asserted in words is checked as well as subtraction performed in digits.
const FORBIDDEN_RELATIONS = [
  /\bthe remaining\b/i,
  /\bthe other\b/i,
  /\brest of (?:the|them)\b/i,
  /\bleftover\b/i,
  /\bthe rest were\b/i,
];

/** True when a sentence both claims a remainder and talks about the gate's verdicts. Either
 *  alone is fine — "the remaining spreads expire next week" is a legitimate sentence. */
function assertsRemainder(sentence: string): boolean {
  if (!/refus|approv|reject/i.test(sentence)) return false;
  return FORBIDDEN_RELATIONS.some((re) => re.test(sentence));
}

export type Verification = {
  ok: boolean;
  /** Numbers found in the prose that match nothing the model was given. */
  unverified: string[];
  checked: number;
};

/** Every value the model is allowed to restate, in every form it might reasonably write it.
 *  A figure of 99432.58 may legitimately appear as 99432.58, 99433, or 99432, and a negative
 *  may lose its sign to the word "minus", so magnitudes are compared, not signed values. */
function allowedValues(facts: unknown): Set<number> {
  const out = new Set<number>();

  const add = (n: number) => {
    if (!Number.isFinite(n)) return;
    const a = Math.abs(n);
    out.add(a);
    out.add(Math.round(a));
    out.add(Math.floor(a));
    out.add(Math.ceil(a));
    out.add(Number(a.toFixed(1)));
    out.add(Number(a.toFixed(2)));
  };

  const walk = (v: unknown) => {
    if (typeof v === "number") return add(v);
    if (typeof v === "string") {
      // Dates are the one string that legitimately becomes digits in the prose:
      // "2026-09-02" is written as "September 2, 2026".
      const m = v.match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (m) {
        add(Number(m[1]));
        add(Number(m[2]));
        add(Number(m[3]));
      }
      return;
    }
    if (Array.isArray(v)) return v.forEach(walk);
    if (v && typeof v === "object") return Object.values(v).forEach(walk);
  };

  walk(facts);
  return out;
}

/** Digit groups separated by thin/non-breaking spaces are one number ("100 000"), and
 *  thousands commas are noise. Normalise both before extracting. */
function normalise(text: string): string {
  return text
    .replace(/[‒–—−‐‑]/g, "-")
    .replace(/(\d)[    ](?=\d{3}\b)/g, "$1")
    .replace(/(\d),(?=\d{3}\b)/g, "$1");
}

/** opts.forbidToday is set when the newest session in the data is not the current one. The
 *  prompt already says so and the model ignores it: told the figures describe the most recent
 *  session and that it is not today, it still opened with "Today, the agent made 60
 *  proposals" and went on to say "in today's session". The date was right in between. A rule
 *  the model is asked to follow is worth something; a rule the server enforces is worth more.
 */
export function verifyBriefing(
  text: string,
  facts: unknown,
  opts: { forbidToday?: boolean } = {}
): Verification {
  const allowed = allowedValues(facts);
  const seen = normalise(text);
  const unverified: string[] = [];
  let checked = 0;

  const matches = (value: number): boolean => {
    const a = Math.abs(value);
    if (allowed.has(a)) return true;
    // A rounded restatement of a real figure is honest, so accept anything within half a
    // unit of a permitted value — but only that. It is not a licence for approximation.
    for (const ok of allowed) {
      if (Math.abs(ok - a) <= 0.5) return true;
    }
    return false;
  };

  for (const m of seen.matchAll(/\d+(?:\.\d+)?/g)) {
    const value = Number(m[0]);
    checked += 1;
    if (!matches(value)) unverified.push(m[0]);
  }

  // Spelled-out numbers dodge the digit scan entirely — "two orders", "four days" — so they
  // are checked too. Only standalone words count; "one of them" is a pronoun, and "the one
  // rule" is not a quantity, so the bare word "one" is exempt.
  for (const m of seen.toLowerCase().matchAll(/\b([a-z]+)\b/g)) {
    const word = m[1];
    if (word === "one") continue;
    const value = WORD_NUMBERS[word];
    if (value === undefined) continue;
    checked += 1;
    if (!matches(value)) unverified.push(word);
  }

  if (opts.forbidToday && /\btoday'?s?\b/i.test(seen)) {
    unverified.push('calls the latest session "today" when it is not today');
  }

  for (const sentence of seen.split(/(?<=[.!?])\s+/)) {
    if (assertsRemainder(sentence)) {
      unverified.push('claims a remainder between proposals and verdicts ("' +
        sentence.trim().slice(0, 60) + '…")');
      break;
    }
  }

  return { ok: unverified.length === 0, unverified: [...new Set(unverified)], checked };
}
