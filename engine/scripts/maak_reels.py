#!/usr/bin/env python3
"""
Maakt de reels van een ronde: elke video staand (1080 bij 1920), met de tekst in
beeld in de eigen stijl, klaar om in te plannen.

    python3 engine/scripts/maak_reels.py mijn-trial-reels/rondes/<naam>
    python3 engine/scripts/maak_reels.py <ronde> --controleer         alleen nakijken, niets maken
    python3 engine/scripts/maak_reels.py <ronde> --opnieuw 03 07       deze opnieuw (de oude gaan naar klaar/oud/)

De ronde staat in <ronde>/ronde.json:

    {"naam": "eerste-ronde",
     "posts": [{"id": "01", "video": "/pad/naar/clip.mp4", "tekst": "Tekst in beeld",
                "caption": "Caption onder de reel", "angle": "pijn", "van": 0, "tot": 8}]}

tekst, angle, van en tot mogen weg. Zonder tekst gaat de video zonder tekst in beeld.

Elke reel onthoudt in klaar/<id>.json waarvan hij gemaakt is (video, stuk, tekst en
stijl). Verandert daar iets aan, dan wordt hij opnieuw gemaakt en gaat de oude naar
klaar/oud/. Een reel wordt eerst apart gemaakt en pas na de controle klaar/<id>.mp4;
een mislukte poging gaat naar klaar/mislukt/. Er wordt niets weggegooid.
Duurt lang: ongeveer zo lang als de video's samen. Geef het commando ruim de tijd.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from instellingen import FONTMAP, InstellingFout, laad, vrije_naam
from slot import SlotFout, slot
from tekstblok import TekstFout, render

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
# Grenzen van Instagram voor een reel via de API (Meta, Reels publishing guide, zoals Zernio hem noemt)
MIN_SEC, MAX_SEC = 3, 90
MAX_CAPTION = 2200


class RondeFout(Exception):
    pass


def lees_ronde(map_, bron=True):
    """Leest en keurt ronde.json. Met bron=False hoeven de oorspronkelijke video's er niet meer te zijn
    (inplannen gebruikt de gemaakte reels in klaar/)."""
    map_ = Path(map_)
    bestand = map_ / "ronde.json"
    if not bestand.exists():
        raise RondeFout(f"{bestand} bestaat niet.")
    try:
        ronde = json.loads(bestand.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RondeFout(f"ronde.json is geen geldig bestand: {e}")
    posts = ronde.get("posts") if isinstance(ronde, dict) else None
    if not isinstance(posts, list) or not posts:
        raise RondeFout("ronde.json heeft geen posts.")
    gezien, fouten = set(), []
    for i, p in enumerate(posts, 1):
        if not isinstance(p, dict):
            fouten.append(f"post {i} is geen blok")
            continue
        pid = p.get("id")
        if not isinstance(pid, str) or not ID_RE.match(pid):
            fouten.append(f"post {i}: id moet letters, cijfers, - of _ zijn (hooguit 40)")
            continue
        if pid in gezien:
            fouten.append(f"post {pid} staat er twee keer in")
        gezien.add(pid)
        video = p.get("video")
        if not isinstance(video, str) or not video:
            fouten.append(f"post {pid}: geen video")
        elif bron and not (map_ / video).expanduser().exists():
            fouten.append(f"post {pid}: video {video} bestaat niet")
        if not isinstance(p.get("caption", ""), str) or len(p.get("caption", "")) > MAX_CAPTION:
            fouten.append(f"post {pid}: de caption is langer dan {MAX_CAPTION} tekens")
        if "tekst" in p and not isinstance(p["tekst"], str):
            fouten.append(f"post {pid}: tekst moet tekst zijn")
        for veld in ("van", "tot"):
            if veld in p and (isinstance(p[veld], bool) or not isinstance(p[veld], (int, float)) or p[veld] < 0):
                fouten.append(f"post {pid}: {veld} moet een aantal seconden zijn")
    if fouten:
        raise RondeFout("In ronde.json klopt iets niet:\n" + "\n".join(f"{n}. {f}" for n, f in enumerate(fouten, 1)))
    return ronde


def video_pad(map_, post):
    return (Path(map_) / post["video"]).expanduser().resolve()


def vingerafdruk(post, cfg):
    """Waarvan een reel gemaakt is. Verandert hier iets, dan hoort de reel niet meer bij de ronde."""
    return {"video": post["video"], "van": post.get("van"), "tot": post.get("tot"),
            "tekst": (post.get("tekst") or "").strip(), "stijl": cfg["tekst"] if (post.get("tekst") or "").strip() else None}


def actueel(map_, post, cfg):
    """Of klaar/<id>.mp4 er is en gemaakt is van precies wat er nu in de ronde en de stijl staat."""
    klaar = Path(map_) / "klaar"
    if not (klaar / f"{post['id']}.mp4").exists() or not (klaar / f"{post['id']}.json").exists():
        return False
    try:
        return json.loads((klaar / f"{post['id']}.json").read_text(encoding="utf-8")) == vingerafdruk(post, cfg)
    except (OSError, json.JSONDecodeError):
        return False


def meet(video):
    """Duur, breedte en hoogte zoals je hem ziet (na draaien), geluid ja of nee, en of hij HDR is."""
    uit = subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)],
                         capture_output=True, text=True)
    if uit.returncode != 0:
        raise RondeFout(f"{Path(video).name} is geen video die te lezen is.")
    info = json.loads(uit.stdout)
    beeld = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if not beeld:
        raise RondeFout(f"{Path(video).name} heeft geen beeld.")
    b, h = int(beeld["width"]), int(beeld["height"])
    draai = 0
    for sd in beeld.get("side_data_list", []) or []:
        if "rotation" in sd:
            draai = int(float(sd["rotation"]))
    draai = draai or int(beeld.get("tags", {}).get("rotate", 0) or 0)
    if abs(draai) % 180 == 90:
        b, h = h, b
    duur = float(info.get("format", {}).get("duration") or beeld.get("duration") or 0)
    return {
        "duur": duur, "breedte": b, "hoogte": h,
        "geluid": any(s.get("codec_type") == "audio" for s in info.get("streams", [])),
        "hdr": beeld.get("color_transfer") in ("arib-std-b67", "smpte2084"),
    }


_hdr_kan = None


def hdr_filter():
    """HDR (zoals een iPhone filmt) naar gewone kleuren, met het eigen scale-filter van ffmpeg 8."""
    global _hdr_kan
    if _hdr_kan is None:
        hulp = subprocess.run([FFMPEG, "-hide_banner", "-h", "filter=scale"], capture_output=True, text=True).stdout
        _hdr_kan = "out_transfer" in hulp
    return "scale=out_primaries=bt709:out_transfer=bt709," if _hdr_kan else ""


def passend(m):
    """Het filter dat het beeld staand maakt. Bijna staand: bijsnijden. Liggend of vierkant: vullen met een wazige versie."""
    verhouding = m["breedte"] / m["hoogte"]
    if 0.5 <= verhouding <= 0.62:
        return "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    return ("split=2[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            "boxblur=30:3,eq=brightness=-0.08[achter];[b]scale=1080:1920:force_original_aspect_ratio=decrease[voor];"
            "[achter][voor]overlay=(W-w)/2:(H-h)/2,setsar=1")


def knip(post, m):
    van = float(post.get("van", 0))
    tot = float(post.get("tot", m["duur"]))
    if tot > m["duur"] + 0.05:
        raise RondeFout(f"post {post['id']}: tot ({tot:g} s) ligt na het einde van de video ({m['duur']:.1f} s).")
    if tot - van < MIN_SEC or tot - van > MAX_SEC:
        raise RondeFout(f"post {post['id']}: een reel moet {MIN_SEC} tot {MAX_SEC} seconden zijn, deze is {tot - van:.1f} s. "
                        "Zet van en tot in ronde.json om een stuk te kiezen.")
    return van, tot - van


def controleer(map_, posts, cfg):
    """Kijkt de posts na die gemaakt moeten worden, zonder iets te maken. Geeft per post de meting terug."""
    metingen, fouten = {}, []
    for p in posts:
        try:
            if not video_pad(map_, p).exists():
                raise RondeFout(f"post {p['id']}: video {p['video']} bestaat niet")
            m = meet(video_pad(map_, p))
            knip(p, m)
            if (p.get("tekst") or "").strip():
                render(p["tekst"], cfg)
            metingen[p["id"]] = m
        except (RondeFout, TekstFout) as e:
            fouten.append(str(e) if str(e).startswith("post ") else f"post {p['id']}: {e}")
    if fouten:
        raise RondeFout("Nog niet klaar om te maken:\n" + "\n".join(f"{n}. {f}" for n, f in enumerate(fouten, 1)))
    return metingen


def wegzetten(bestand, map_, stam):
    """Zet een bestand opzij in map_ (oud/ of mislukt/), onder een naam die nog niet bestaat. Gooit niets weg."""
    if bestand.exists():
        doel = vrije_naam(map_, stam, bestand.suffix)
        bestand.rename(doel)


def maak_een(map_, post, m, cfg):
    klaar = Path(map_) / "klaar"
    klaar.mkdir(exist_ok=True)
    uit = klaar / f"{post['id']}.mp4"
    bezig = klaar / f".{post['id']}.bezig.mp4"
    wegzetten(bezig, klaar / "mislukt", post["id"])   # een halve poging van eerder, bijvoorbeeld na een onderbreking
    van, duur = knip(post, m)
    tekst = (post.get("tekst") or "").strip()
    tijdelijk = klaar / f".{post['id']}-tekst.png"
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-n", "-ss", f"{van:.3f}", "-t", f"{duur:.3f}",
           "-i", str(video_pad(map_, post))]
    if tekst:
        render(tekst, cfg).save(tijdelijk)
        cmd += ["-i", str(tijdelijk)]
    if not m["geluid"]:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    kleur = hdr_filter() if m["hdr"] else ""
    if m["hdr"] and not kleur:
        print(f"Let op: post {post['id']} is HDR en deze ffmpeg kan dat niet omzetten; de kleuren worden flets. "
              "Werk ffmpeg bij met: brew upgrade ffmpeg")
    graaf = f"[0:v]{kleur}{passend(m)}[beeld];"
    # De kleurlabels horen bij het beeld zelf; alleen als vlag bij het opslaan bleven ze leeg (gemeten met ffprobe)
    labels = "format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709"
    graaf += f"[beeld][1:v]overlay=0:0,{labels}[v];" if tekst else f"[beeld]{labels}[v];"
    # Is het geluid korter dan het beeld, dan vult stilte aan; anders zou -shortest de reel inkorten
    graaf += f"[{0 if m['geluid'] else (2 if tekst else 1)}:a:0]apad[a]"
    cmd += ["-filter_complex", graaf, "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-maxrate", "8M", "-bufsize", "16M", "-r", "30",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-shortest", "-movflags", "+faststart", str(bezig)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        tijdelijk.unlink(missing_ok=True)   # eigen hulpbestand van deze stap
    try:
        if r.returncode != 0:
            raise RondeFout(f"post {post['id']}: ffmpeg lukte niet: {r.stderr.strip()[-400:]}")
        na = meet(bezig)
        if (na["breedte"], na["hoogte"]) != (1080, 1920) or abs(na["duur"] - duur) > 0.25 or not na["geluid"]:
            raise RondeFout(f"post {post['id']}: de gemaakte reel klopt niet ({na['breedte']}x{na['hoogte']}, {na['duur']:.2f} s).")
    except RondeFout:
        wegzetten(bezig, klaar / "mislukt", post["id"])
        raise
    plaatje = klaar / f"{post['id']}.jpg"
    wegzetten(plaatje, klaar / "oud", post["id"])
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-n", "-ss", f"{min(1.0, duur / 2):.2f}", "-i", str(bezig),
                    "-frames:v", "1", "-q:v", "3", str(plaatje)], check=True)
    # Eerst opschrijven waarvan hij gemaakt is, dan pas de reel op zijn plek: zonder beide telt hij niet als klaar
    (klaar / f"{post['id']}.json").write_text(json.dumps(vingerafdruk(post, cfg), ensure_ascii=False) + "\n", encoding="utf-8")
    bezig.rename(uit)
    return uit


def contactvel(map_, ids):
    klaar = Path(map_) / "klaar"
    plaatjes = [(i, klaar / f"{i}.jpg") for i in ids if (klaar / f"{i}.jpg").exists()]
    if not plaatjes:
        return None
    kol, b, h, label = 4, 270, 480, 40
    rijen = (len(plaatjes) + kol - 1) // kol
    vel = Image.new("RGB", (kol * (b + 10) + 10, rijen * (h + label + 10) + 10), "white")
    font = ImageFont.truetype(str(FONTMAP / "Inter-ExtraBold.ttf"), 26)
    for n, (pid, pad) in enumerate(plaatjes):
        x, y = 10 + (n % kol) * (b + 10), 10 + (n // kol) * (h + label + 10)
        vel.paste(Image.open(pad).convert("RGB").resize((b, h)), (x, y))
        ImageDraw.Draw(vel).text((x, y + h + 6), pid, font=font, fill="black")
    uit = vrije_naam(Path(map_), "contactvel", ".jpg")
    vel.save(uit, quality=88)
    return uit


def overzicht(map_, ronde, cfg):
    regels = [f"# Ronde {ronde.get('naam', Path(map_).name)}", "",
              "| id | klaar | tekst in beeld | caption | angle |", "|---|---|---|---|---|"]
    for p in ronde["posts"]:
        cel = lambda s: (s or "").replace("\n", " ").replace("|", "/")[:80]
        regels.append(f"| {p['id']} | {'ja' if actueel(map_, p, cfg) else 'nee'} | {cel(p.get('tekst'))} "
                      f"| {cel(p.get('caption'))} | {cel(p.get('angle'))} |")
    (Path(map_) / "overzicht.md").write_text("\n".join(regels) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ronde", help="de map van de ronde, met ronde.json erin")
    ap.add_argument("--controleer", action="store_true", help="alleen nakijken, niets maken")
    ap.add_argument("--opnieuw", nargs="+", metavar="ID", help="deze posts opnieuw maken; de oude gaan naar klaar/oud/")
    a = ap.parse_args()
    map_ = Path(a.ronde).expanduser().resolve()
    try:
        cfg = laad()
        ronde = lees_ronde(map_, bron=False)
        ids = {p["id"] for p in ronde["posts"]}
        for pid in a.opnieuw or []:
            if pid not in ids:
                raise RondeFout(f"Post {pid} staat niet in deze ronde.")
        klaar = map_ / "klaar"
        # Te maken: wat er nog niet is, wat gevraagd is, en wat niet meer past bij de ronde of de stijl
        verouderd = [p["id"] for p in ronde["posts"] if (klaar / f"{p['id']}.mp4").exists() and not actueel(map_, p, cfg)]
        te_maken = [p for p in ronde["posts"] if not actueel(map_, p, cfg) or p["id"] in (a.opnieuw or [])]
        metingen = controleer(map_, te_maken, cfg)
    except (RondeFout, InstellingFout) as e:
        sys.exit(str(e))
    if a.controleer:
        print(f"Alles klopt: {len(te_maken)} te maken, {len(ronde['posts']) - len(te_maken)} staan er al goed."
              + (f" Opnieuw omdat video, stuk, tekst of stijl veranderde: {', '.join(verouderd)}." if verouderd else ""))
        return
    gemaakt = []
    try:
        with slot(map_, "maken"):
            for p in te_maken:
                for ext in ("mp4", "json"):
                    wegzetten(klaar / f"{p['id']}.{ext}", klaar / "oud", p["id"])
                try:
                    maak_een(map_, p, metingen[p["id"]], cfg)
                except (RondeFout, TekstFout) as e:
                    sys.exit(f"Gestopt bij post {p['id']}: {e}\nWat al gemaakt is, blijft staan; opnieuw draaien gaat verder.")
                gemaakt.append(p["id"])
                print(f"gemaakt: {p['id']}" + (" (opnieuw: video, stuk, tekst of stijl veranderde)" if p["id"] in verouderd else ""))
    except SlotFout as e:
        sys.exit(str(e))
    finally:
        overzicht(map_, ronde, cfg)
    vel = contactvel(map_, [p["id"] for p in ronde["posts"]]) if gemaakt else None
    print(f"Klaar: {len(gemaakt)} gemaakt, {len(ronde['posts']) - len(gemaakt)} stonden er al goed. Reels in {klaar}.")
    if vel:
        print(f"Contactvel: {vel}")


if __name__ == "__main__":
    main()
