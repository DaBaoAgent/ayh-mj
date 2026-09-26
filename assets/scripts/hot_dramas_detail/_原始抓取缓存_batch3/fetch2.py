# -*- coding: utf-8 -*-
"""Second fetch batch."""
import re, os, html
import requests

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_fetch")
os.makedirs(OUT, exist_ok=True)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

TARGETS = {
    "juben_kaichang": "https://www.juben.pro/a/1-1781.html",
    "juben_taici": "https://www.juben.pro/a/1-1788.html",
    "juben_study2": "https://www.juben.pro/study?page=2",
    "qq_tuwei": "https://news.qq.com/rain/a/20251015A079B800",
    "qq_enemy": "https://news.qq.com/rain/a/20260514A0817600",
    "nc_enemy": "https://www.163.com/dy/article/KTFM0M5N0552POWV.html",
    "sina_jiangjun": "https://www.sina.cn/news/detail/5300006530581053.html",
    "xinent_enemy3": "https://m.xinent.net/web/info/807049-3.html",
}

def clean(h):
    h = re.sub(r"(?is)<script.*?</script>", " ", h)
    h = re.sub(r"(?is)<style.*?</style>", " ", h)
    h = re.sub(r"(?is)<noscript.*?</noscript>", " ", h)
    h = re.sub(r"(?is)<!--.*?-->", " ", h)
    h = re.sub(r"(?is)<br\s*/?>", "\n", h)
    h = re.sub(r"(?is)</(p|div|li|h[1-6]|tr)>", "\n", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    h = html.unescape(h)
    h = re.sub(r"[ \t\u00a0\u3000]+", " ", h)
    h = re.sub(r"\n\s*\n+", "\n", h)
    return h.strip()

ok, fail = [], []
for name, url in TARGETS.items():
    got = False
    last = ""
    for use_proxy in (False, True):
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
                             timeout=25)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding or "utf-8"
                txt = clean(r.text)
                with open(os.path.join(OUT, name + ".txt"), "w", encoding="utf-8") as f:
                    f.write(txt)
                ok.append((name, len(txt)))
                got = True
                break
            last = "HTTP %s" % r.status_code
        except Exception as e:
            last = str(e)[:80]
    if not got:
        fail.append((name, last))

print("OK:", ok)
print("FAIL:", fail)
