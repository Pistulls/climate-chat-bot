// Text handling that matches the service (src/climate_chat/service/api.py): trim, then
// normalise to NFC, then count code points. An emoji or an accented letter is one
// character, even when the accent was typed as a separate combining mark.

export function clean(text: string): string {
  return text.trim().normalize("NFC");
}

export function charCount(text: string): number {
  // Spreading a string splits it into code points, not UTF-16 units.
  return [...clean(text)].length;
}
