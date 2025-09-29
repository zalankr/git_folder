import requests
import json
import keyring

# key 불러오기
app_key = keyring.get_password('kis63692011_key', 'nkr')
app_secret = keyring.get_password('kis63692011_secret', 'nkr')

## 토큰 발급받기
# base url
url_base = "https://openapi.koreainvestment.com:9443"

# information
headers = {"content-type": "application/json"}
path = "oauth2/tokenP"
body = {
    "grant_type": "client_credentials",
    "appkey": app_key,
    "appsecret": app_secret
}

url = f"{url_base}/{path}"

#토큰 발급요청
token = requests.post(url, headers=headers, data=json.dumps(body))
access_token = token.json()['access_token']

# 주문 등에 쓰이는 hashkey 함수 만들기
def hashkey(datas):
    path = "uapi/hashkey"
    url = f"{url_base}/{path}"
    headers = {
        'content-Type': 'application/json',
        'appKey': app_key,
        'appSecret': app_secret,
    }
    res = requests.post(url, headers=headers, data=json.dumps(datas))
    hashkey = res.json()["HASH"]

    return hashkey

# 한국주식 현재가 조회
def current_price_KR(ticker):
    path = "uapi/domestic-stock/v1/quotations/inquire-price"
    url = f"{url_base}/{path}"

    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appKey": app_key,
        "appSecret": app_secret,
        "tr_id": "FHKST01010100"
    }

    params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker}

    search = requests.get(url, headers=headers, params=params)
    search.json()['output']['stck_prpr']
    return search



print(current_price_KR("005930").json()['output']['stck_prpr'])
