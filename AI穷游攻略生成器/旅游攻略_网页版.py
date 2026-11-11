import webbrowser
from flask import Flask, request
from 旅游攻略 import clean_collect, AI_collect
from render import FORM_HTML, render_result

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        return FORM_HTML
    city = request.form.get('city').strip() or '北京'
    popular_lst = request.form.get('popular_lst').strip().split() or ['公园', '博物馆', '文创园']
    black_lst = request.form.get('black_lst').strip().split() or []
    print(f'[参数] 城市={city}, 想去类型={popular_lst}, 不想去={black_lst}')
    spots = clean_collect(city, black_lst, popular_lst)
    if not spots:
        return '<div style="text-align:center;padding:80px 20px;"><h2 style="color:#dc3545;">❌ 未查询到任何景点，请换个城市试试</h2><button style="margin-top:20px;padding:10px 28px;background:#2c7be5;color:white;border:none;border-radius:8px;cursor:pointer;font-size:14px;" onclick="location.href=\'/\'">返回首页</button></div>'
    AI_collect(spots, city)
    return render_result(spots, city)

if __name__ == '__main__':
    print("=" * 50)
    print("✅ 网页版攻略生成器已启动！")
    print("🌐 即将自动打开浏览器：http://127.0.0.1:5000")
    print("=" * 50)
    webbrowser.open('http://127.0.0.1:5000')
    app.run(debug=False, use_reloader=False)