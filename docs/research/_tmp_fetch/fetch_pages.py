# -*- coding: utf-8 -*-
"""Fetch + clean web pages to txt. Usage: python fetch_pages.py"""
import re, sys, os, html
import requests

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_fetch")
os.makedirs(OUT, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

TARGETS = {
    "baike_dongzhi": "https://baike.baidu.com/item/%E9%82%A3%E5%B9%B4%E5%86%AC%E8%87%B3/67474713",
    "baike_furan": "https://baike.baidu.com/item/%E5%A4%8D%E7%87%83/67812566",
    "baike_weiduoliya": "https://baike.baidu.com/item/%E4%BA%B2%E7%88%B1%E7%9A%84%E7%BB%B4%E5%A4%9A%E5%88%A9%E4%BA%9A%E6%B8%AF/67863904",
    "baike_baiquan": "https://baike.baidu.com/item/%E8%B4%A5%E7%8A%AC%E4%B8%8E%E5%A4%A9%E9%B9%85%E9%A2%88/67638789",
    "baike_enemy": "https://baike.baidu.com/item/ENEMY/1600491",
    "baike_yuqun": "https://baike.baidu.com/item/%E9%B1%BC%E7%BE%A4%E8%B7%9F%E7%9D%80%E6%B8%B8%E5%90%91%E9%99%86%E5%9C%B0",
    "baike_jiangjun": "https://baike.baidu.com/item/%E5%B0%86%E5%86%9B%E8%AF%B7%E8%87%AA%E9%87%8D",
    "huxiu": "https://m.huxiu.com/article/2360429.html",
    "juben": "https://www.juben.pro/a/1-1783.html",
    "bianews": "https://www.bianews.com/news/details?id=176812",
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
    for use_proxy in (False, True):
        try:
            if use_proxy:
                r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
                                 timeout=25, proxies={"http": None, "https": None})
            else:
                r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
                                 timeout=25)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding or "utf-8"
                txt = clean(r.text)
                with open(os.path.join(OUT, name + ".txt"), "w", encoding="utf-8") as f:
                    f.write(txt)
                ok.append((name, len(txt), "proxy" if use_proxy else "direct"))
                got = True
                break
            else:
                last = "HTTP %s" % r.status_code
        except Exception as e:
            last = str(e)[:80]
    if not got:
        fail.append((name, last))

print("OK:", ok)
print("FAIL:", fail)
