from flask import Flask, request, abort
from bs4 import BeautifulSoup
import requests
import os

app = Flask(__name__)
@app.route("/astro_api", methods=['GET'])
def astro_api():
    if request.method == 'GET':
        num = int(request.values['num'])
    if (num > 11) or (num < 0):
        exit()
    # 原始 HTML 程式碼
    r = requests.get('http://astro.click108.com.tw/daily_%d.php?iAstro=%d'%(num,num))
    # 以 Beautiful Soup 解析 HTML 程式碼
    soup = BeautifulSoup(r.text, 'html.parser')
    astro = soup.select("div.TODAY_CONTENT > h3")[0]
    items = soup.select("div.TODAY_CONTENT > p")
    resp_data = astro.text+"<br>"
    for a in items:
        resp_data += a.text+"<br>"
    return resp_data

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)