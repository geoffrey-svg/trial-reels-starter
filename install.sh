#!/bin/bash
# Zet klaar wat de Trial Reels Starter nodig heeft op een Mac: ffmpeg en twee Python-onderdelen.
# Veilig om opnieuw te draaien: wat er al staat, wordt overgeslagen.
set -e

groen() { printf "\033[32m%s\033[0m\n" "$1"; }
stap()  { printf "\n\033[1m== %s ==\033[0m\n" "$1"; }

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew ontbreekt (de gereedschapskist waarmee een Mac software installeert)."
  echo "Installeer het eerst via https://brew.sh en draai dit script daarna opnieuw."
  echo "Werk je met Claude Code: vraag Claude om je er doorheen te helpen."
  exit 1
fi

stap "ffmpeg (video's maken)"
if command -v ffmpeg >/dev/null 2>&1 && ffmpeg -hide_banner -h filter=scale 2>/dev/null | grep -q out_transfer; then
  groen "staat er al"
else
  # Versie 8 of nieuwer zet iPhone-video's in HDR om naar gewone kleuren
  brew list ffmpeg >/dev/null 2>&1 && brew upgrade ffmpeg || brew install ffmpeg
fi

stap "Python (Pillow voor de tekst in beeld, fontTools om lettertypes na te kijken)"
if ! python3 -c "import sys" >/dev/null 2>&1; then
  brew install python
fi
if python3 -c "import PIL, fontTools" >/dev/null 2>&1; then
  groen "staat er al"
else
  python3 -m pip install --user --quiet "Pillow>=10" "fonttools>=4" 2>/dev/null \
    || python3 -m pip install --user --break-system-packages --quiet "Pillow>=10" "fonttools>=4"
fi

if [ "$1" = "--metricool" ]; then
  stap "cloudflared (zet een video even openbaar, zodat Metricool hem kan ophalen)"
  if command -v cloudflared >/dev/null 2>&1; then groen "staat er al"; else brew install cloudflared; fi
fi

stap "Controle"
python3 -c "import PIL, fontTools, zoneinfo; print('Python-onderdelen: in orde')"
ffmpeg -hide_banner -version | head -1
groen "Klaar. Open deze map in Claude Code en zeg: start setup"
