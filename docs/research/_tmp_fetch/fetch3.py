# -*- coding: utf-8 -*-
import re, os, html
import requests

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_fetch")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

TARGETS = {
    "sohu_yuqun": "https://www.sohu.com/a/1028424030_482286",
    "nc_top10": "https://www.163.com/dy/article/KTBTKGLV0556BRW3.html",
    "em_yuqun": "https://wap.eastmoney.com/a/202603193677824445.html",
    "dgc_yuqun": "https://www.duanjugongcheng.com/cn/bangdan/ju/yu-qun-gen-zhe-you-xiang-lu-di-2",
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
    got, last = False, ""
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}, timeout=25)
        if r.status_code == 200:
            r.encoding = r.apparent_encoding or "utf-8"
            txt = clean(r.text)
            with open(os.path.join(OUT, name + ".txt"), "w", encoding="utf-8") as f:
                f.write(txt)
            ok.append((name, len(txt)))
            got = True
        else:
            last = "HTTP %s" % r.status_code
    except Exception as e:
        last = str(e)[:80]
    if not got:
        fail.append((name, last))
print("OK:", ok)
print("FAIL:", fail)
