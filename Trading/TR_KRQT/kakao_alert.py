import requests
import json

tokens = None

#파일 경로입니다.
kakao_token_file_path = "/var/autobot/kakao/kakao_token.json"
try:
    #이 부분이 파일을 읽어서 리스트에 넣어주는 로직입니다. 
    with open(kakao_token_file_path, 'r') as json_file:
        tokens = json.load(json_file)

except Exception as e:
    print("Exception", e)


url="https://kapi.kakao.com/v2/api/talk/memo/default/send"



def SendMessage(msg):
    try:
        headers={
            "Authorization" : "Bearer " + tokens["access_token"]
        }
        data={
            "template_object": json.dumps({
                "object_type":"text",
                "text":msg,
                "link":{
                    "web_url": "https://blog.naver.com/zacra",
                    "mobile_web_url": "https://blog.naver.com/zacra"
                }
            })
        }

        response = requests.post(url, headers=headers, data=data)
        if response.json().get('result_code') == 0:
            print('메시지를 성공적으로 보냈습니다.')
        else:
            print('메시지를 성공적으로 보내지 못했습니다. 오류메시지 : ' + str(response.json()))



    except Exception as ex:
        print(ex)