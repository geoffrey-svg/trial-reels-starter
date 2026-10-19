"""
Een nagemaakte Zernio voor de tests, gebouwd naar Zernio's eigen beschrijving van de API
(zernio.com/openapi.json, gelezen 19 okt 2026): dezelfde paden, velden en statuscodes.
Draait op 127.0.0.1 in een eigen draad; de test kan storingen aanzetten.
"""

import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

SLEUTEL = "sk_" + "a1" * 32


class NepZernio:
    def __init__(self):
        self.accounts = []          # zoals GET /v1/accounts ze geeft
        self.profielen = [{"_id": "p" * 24, "name": "Trial Reels"}]
        self.posts = {}             # _id -> post
        self.idem = {}              # Idempotency-Key -> _id
        self.uploads = {}           # key -> grootte
        self.cijfers = {}           # accountId -> lijst posts zoals GET /v1/analytics ze geeft
        self.aanroepen = []         # (methode, pad)
        self.storing = []           # lijst van ("pad-patroon", soort): een statuscode, "slik" (wel doen, geen antwoord),
                                    # "bezig" (409 idempotency_conflict) of ("traag", seconden)
        self.publiceer_faalt = False  # een post die meteen gepubliceerd wordt (tijd voorbij), mislukt dan op Instagram
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.basis = f"http://127.0.0.1:{self.server.server_address[1]}/api/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def tel(self, methode, patroon):
        return sum(1 for m, p in self.aanroepen if m == methode and re.search(patroon, p))

    def _handler(nep):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _stuur(self, code, data, koppen=None):
                lijf = json.dumps(data).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(lijf)))
                for k, v in (koppen or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(lijf)

            def _lijf(self):
                n = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(n) if n else b""

            def _storing(self, pad):
                for i, (patroon, soort) in enumerate(nep.storing):
                    if re.search(patroon, f"{self.command} {pad}"):
                        nep.storing.pop(i)
                        return soort
                return None

            def _doe(self):
                url = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                nep.aanroepen.append((self.command, url.path))
                ruw = self._lijf()
                if url.path.startswith("/upload/") and self.command == "PUT":
                    nep.uploads[url.path.split("/")[-1]] = len(ruw)
                    self.send_response(200)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if self.headers.get("Authorization") != f"Bearer {SLEUTEL}":
                    return self._stuur(401, {"error": "Unauthorized"})
                storing = self._storing(url.path)
                if isinstance(storing, int):
                    return self._stuur(storing, {"error": "storing"}, {"Retry-After": "1"} if storing == 429 else None)
                if storing == "bezig":
                    return self._stuur(409, {"error": "A request with this Idempotency-Key is still being processed", "code": "idempotency_conflict"}, {"Retry-After": "1"})
                if isinstance(storing, tuple) and storing[0] == "traag":
                    time.sleep(storing[1])
                pad = url.path.removeprefix("/api/v1")
                body = json.loads(ruw) if ruw else None
                antwoord = self._route(pad, q, body)
                if storing == "slik":
                    self.close_connection = True
                    return
                self._stuur(*antwoord)

            def _route(self, pad, q, body):
                m = self.command
                if m == "GET" and pad == "/accounts":
                    return 200, {"accounts": [a for a in nep.accounts if a["platform"] == q.get("platform", a["platform"])],
                                 "hasAnalyticsAccess": True}
                if m == "GET" and pad == "/profiles":
                    return 200, {"profiles": nep.profielen}
                if m == "POST" and pad == "/profiles":
                    p = {"_id": uuid.uuid4().hex[:24], "name": body["name"]}
                    nep.profielen.append(p)
                    return 201, {"message": "Profile created successfully", "profile": p}
                if m == "GET" and pad == "/connect/instagram":
                    if not q.get("profileId"):
                        return 400, {"error": "profileId required"}
                    return 200, {"authUrl": f"https://www.instagram.com/oauth/authorize?state={q['profileId']}"}
                if m == "POST" and pad == "/media/presign":
                    if body.get("contentType") != "video/mp4" or not body.get("filename"):
                        return 400, {"error": "INVALID_FIELD_VALUE"}
                    key = uuid.uuid4().hex
                    host = nep.basis.removesuffix("/api/v1")
                    return 200, {"uploadUrl": f"{host}/upload/{key}", "publicUrl": f"https://media.zernio.test/{key}.mp4",
                                 "key": key, "expiresIn": 3600}
                if m == "POST" and pad == "/posts":
                    return self._maak_post(body)
                if m == "GET" and pad == "/posts":
                    lijst = list(nep.posts.values())
                    if q.get("tags"):
                        lijst = [p for p in lijst if all(t in p["tags"] for t in q["tags"].split(","))]
                    if q.get("accountId"):
                        lijst = [p for p in lijst if p["platforms"][0]["accountId"]["_id"] == q["accountId"]]
                    if q.get("status"):
                        lijst = [p for p in lijst if p["status"] == q["status"]]
                    limit, page = int(q.get("limit", 10)), int(q.get("page", 1))
                    if limit > 500:
                        return 400, {"error": "limit"}
                    deel = lijst[(page - 1) * limit: page * limit]
                    return 200, {"posts": deel, "pagination": {"page": page, "limit": limit, "total": len(lijst),
                                                               "pages": max(1, -(-len(lijst) // limit))}}
                if m == "GET" and pad.startswith("/posts/"):
                    post = nep.posts.get(pad.split("/")[-1])
                    return (200, {"post": post}) if post else (404, {"error": "Not found"})
                if m == "DELETE" and pad.startswith("/posts/"):
                    # Zernio: het hele record verdwijnt, daarna geeft ophalen 404
                    return (200, {"message": "Post deleted"}) if nep.posts.pop(pad.split("/")[-1], None) else (404, {"error": "Not found"})
                if m == "GET" and pad == "/analytics":
                    lijst = nep.cijfers.get(q.get("accountId"), [])
                    limit, page = int(q.get("limit", 50)), int(q.get("page", 1))
                    return 200, {"overview": {}, "posts": lijst[(page - 1) * limit: page * limit], "pagination": {}}
                return 404, {"error": f"onbekend: {m} {pad}"}

            def _maak_post(self, body):
                sleutel = self.headers.get("Idempotency-Key")
                if sleutel and sleutel in nep.idem:
                    return 200, {"post": nep.posts[nep.idem[sleutel]]}
                plat = (body.get("platforms") or [{}])[0]
                if not body.get("platforms") or plat.get("platform") != "instagram":
                    return 400, {"error": "platforms required"}
                acc = next((a for a in nep.accounts if a["_id"] == plat.get("accountId")), None)
                if not acc:
                    return 400, {"error": "account not found"}
                if acc.get("needsReconnection") or acc.get("enabled") is False:
                    return 403, {"error": "Account is not enabled for posting", "code": "ACCOUNT_NOT_ENABLED_FOR_POSTING"}
                media = body.get("mediaItems") or []
                if len(media) != 1 or not media[0]["url"].startswith("https://media.zernio.test/") \
                        or media[0]["url"].split("/")[-1][:-4] not in nep.uploads:
                    return 400, {"error": "media not uploaded"}
                tijd = datetime.fromisoformat(body["scheduledFor"])
                if tijd.tzinfo is None:
                    tijd = tijd.replace(tzinfo=ZoneInfo(body.get("timezone") or "UTC"))
                trial = (plat.get("platformSpecificData") or {}).get("trialParams")
                post = {
                    "_id": uuid.uuid4().hex[:24], "content": body.get("content", ""), "mediaItems": media,
                    "scheduledFor": tijd.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "timezone": body.get("timezone"), "status": "scheduled", "tags": body.get("tags") or [],
                    # Zernio geeft het account hier als volledig object terug
                    "platforms": [{"platform": "instagram", "accountId": {"_id": acc["_id"], "username": acc["username"], "platform": "instagram"},
                                   "status": "pending",
                                   **({"isTrialReel": True, "trialGraduationStrategy": trial["graduationStrategy"]} if trial else {})}],
                }
                code = 201
                # Zernio: een scheduledFor die al voorbij is, wordt meteen in hetzelfde verzoek gepubliceerd (207 als dat mislukt)
                if tijd <= datetime.now(timezone.utc):
                    if nep.publiceer_faalt:
                        post["status"] = "failed"
                        post["platforms"][0].update(status="failed", errorMessage="Media upload failed")
                        code = 207
                    else:
                        post["status"] = "published"
                        post["platforms"][0].update(status="published", platformPostUrl="https://www.instagram.com/reel/nu/")
                nep.posts[post["_id"]] = post
                if sleutel:
                    nep.idem[sleutel] = post["_id"]
                return code, {"message": "Post scheduled successfully", "post": post}

            do_GET = do_POST = do_PUT = do_DELETE = _doe

        return H
