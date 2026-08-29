// Fixed categorical assignment, never cycled — per the dataviz skill's rule.
// cash deliberately isn't a real categorical slot: it's "no trade," not a strategy on
// par with the other three, so it gets muted gray rather than a hue from the ramp.
export const STRATEGY_STYLE: Record<
  string,
  { label: string; light: string; dark: string }
> = {
  bull_call_spread: { label: "Bull call spread", light: "#2a78d6", dark: "#3987e5" }, // slot 1 blue
  bear_put_spread: { label: "Bear put spread", light: "#eb6834", dark: "#d95926" }, // slot 2 orange
  iron_condor: { label: "Iron condor", light: "#1baf7a", dark: "#199e70" }, // slot 3 aqua
  cash: { label: "Cash", light: "#898781", dark: "#898781" }, // muted, not a categorical slot
};

export function strategyLabel(strategy: string | undefined | null): string {
  if (!strategy) return "—";
  return STRATEGY_STYLE[strategy]?.label ?? strategy;
}
