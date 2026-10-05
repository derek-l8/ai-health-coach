// Interpret device-local wall times without silently selecting a repeated hour.
export function localTime(date) {
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return shifted.toISOString().slice(0, 16);
}

export function timeCandidates(value) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return [];
  const first = new Date(value);
  if (!Number.isFinite(first.getTime()) || localTime(first) !== value) return [];
  // Probe nearby offsets, including half-hour and date-line transitions.
  // Validate each candidate against the original wall time, not a fixed DST delta.
  const offsets = new Set();
  for (let hours = -48; hours <= 48; hours += 6) {
    offsets.add(new Date(first.getTime() + hours * 3600000).getTimezoneOffset());
  }
  return [...new Set([...offsets].map(offset => {
    const date = new Date(first.getTime() +
      (offset - first.getTimezoneOffset()) * 60000);
    return localTime(date) === value ? date.toISOString() : null;
  }).filter(Boolean))].sort();
}

export function timestamp(value, occurrence = "") {
  const candidates = timeCandidates(value);
  if (!candidates.length) {
    throw new Error("That local time is invalid or does not exist in your timezone.");
  }
  if (candidates.length > 1 && !candidates.includes(occurrence)) {
    throw new Error("That local time occurs twice. Choose its first or second occurrence.");
  }
  return candidates.length === 1 ? candidates[0] : occurrence;
}
