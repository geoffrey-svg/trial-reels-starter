"""
Een nagemaakte Metricool voor de tests, naar wat er op echte Metricool-accounts gemeten is
(Skills/content-planner en Projecten/Trial Reels Systeem in het OS van de maker, aug en sep 2026):
X-Mc-Auth met de token, userId en blogId als parameter, posts in /v2/scheduler/posts met
publicationDate {dateTime, timezone}, providers met status PENDING, PUBLISHED of ERROR, de kopie
van de video naar static.metricool.com bij saveExternalMediaFiles, en /stats/instagram/reels.
"""

import json
import re
import threading
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

TOKEN = "mc" + "x7" * 20
USER = "4242424"


class NepMetricool:
    def __init__(self):
        self.merken = []        # zoals /admin/simpleProfiles ze geeft
        self.volgers = {}       # blogId -> aantal
        self.posts = {}         # id -> post
        self.stats = {}         # blogId -> lijst reels
        self.aanroepen = []
        self.storing = []       # ("pad-patroon", "slik" of statuscode)
        self.volgende_id = 900000
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.basis = f"http://127.0.0.1:{self.server.server_address[1]}/api"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def publiceer(self, post_id, code, fout=None):
        """Doe alsof het geplande moment voorbij is: online met een url, of mislukt met een reden."""
        ig = self.posts[str(post_id)]["providers"][0]
        if fout:
            ig.update(status="ERROR", detailedStatus=fout)
        else:
            ig.update(status="PUBLISHED", publicUrl=f"https://www.instagram.com/reel/{code}/")

    def _handler(nep):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _stuur(self, code, data):
                lijf = json.dumps(data).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(lijf)))
                self.end_headers()
                self.wfile.write(lijf)

            def _doe(self):
                url = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n)) if n else None
                nep.aanroepen.append((self.command, url.path, q))
                if self.headers.get("X-Mc-Auth") != TOKEN or q.get("userId") != USER:
                    return self._stuur(401, {"message": "Unauthorized"})
                storing = None
                for i, (patroon, soort) in enumerate(nep.storing):
                    if re.search(patroon, f"{self.command} {url.path}"):
                        storing = nep.storing.pop(i)[1]
                        break
                if isinstance(storing, int):
                    return self._stuur(storing, {"message": "storing"})
                antwoord = self._route(url.path.removeprefix("/api"), q, body)
                if storing == "slik":
                    self.close_connection = True
                    return
                self._stuur(*antwoord)

            def _route(self, pad, q, body):
                m = self.command
                if m == "GET" and pad == "/admin/simpleProfiles":
                    return 200, nep.merken
                if m == "GET" and pad == "/v2/analytics/timelines":
                    blog = q.get("blogId")
                    if blog not in nep.volgers or q.get("metric") != "followers":
                        return 400, {"message": "metric not available"}
                    return 200, {"data": [{"metric": "followers", "values": [
                        {"dateTime": q["from"], "value": nep.volgers[blog] - 3}, {"dateTime": q["to"], "value": nep.volgers[blog]}]}]}
                if m == "GET" and pad == "/v2/scheduler/posts":
                    van, tot = datetime.fromisoformat(q["start"]), datetime.fromisoformat(q["end"])
                    return 200, {"data": [p for p in nep.posts.values() if p["_blog"] == q.get("blogId")
                                          and van <= datetime.fromisoformat(p["publicationDate"]["dateTime"]) < tot]}
                if m == "GET" and pad.startswith("/v2/scheduler/posts/"):
                    p = nep.posts.get(pad.split("/")[-1])
                    return (200, {"data": p}) if p and p["_blog"] == q.get("blogId") else (404, {"message": "Not found"})
                if m == "POST" and pad == "/v2/scheduler/posts":
                    if not q.get("blogId") or "publicationDate" not in body or not body.get("providers"):
                        return 400, {"message": "bad request"}
                    ZoneInfo(body["publicationDate"]["timezone"])
                    media = body["media"]
                    if body.get("saveExternalMediaFiles"):
                        # Metricool haalt de video op terwijl de post gemaakt wordt; lukt dat, dan staat hij op static.metricool.com
                        try:
                            with urllib.request.urlopen(media[0], timeout=5) as r:
                                if len(r.read()) > 0:
                                    media = [f"https://static.metricool.com/nep/{nep.volgende_id}.mp4"]
                        except Exception:
                            pass
                    post = {"id": nep.volgende_id, "_blog": q["blogId"], "text": body.get("text", ""), "media": media,
                            "publicationDate": body["publicationDate"], "draft": body.get("draft", False),
                            "instagramData": body.get("instagramData"),
                            "providers": [{"network": p["network"], "status": "PENDING"} for p in body["providers"]]}
                    nep.posts[str(nep.volgende_id)] = post
                    nep.volgende_id += 1
                    return 200, {"data": post}
                if m == "GET" and pad == "/stats/instagram/reels":
                    return 200, nep.stats.get(q.get("blogId"), [])
                return 404, {"message": f"onbekend: {m} {pad}"}

            do_GET = do_POST = _doe

        return H
