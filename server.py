from flask import Flask, render_template, request, make_response, jsonify
from flask import redirect
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_restful import abort, Api

from forms.news import NewsForm
from forms.user import RegisterForm, LoginForm
from data.news import News
from data.trains import Trains
from data.lines import Lines
from data import db_session, news_api, news_resources
from data.users import User
import sqlite3
import pygame
import os
import requests
import json
import asyncio
import aiohttp
from aiohttp import ClientSession
from threading import Thread
import time
import random

app = Flask(__name__)
api = Api(app)
app.config['SECRET_KEY'] = 'yandexlyceum_secret_key'
login_manager = LoginManager()
login_manager.init_app(app)
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

API_WEATHER = "1a7eb0d3bedabab539e379e196eae654"
API_GEOCODE_MAPS = "40d1649f-0493-4b70-98ba-98533de7710b"
CONDITIONS_RU = {"clear": "ясно", "partly-cloudy": "малооблачно", "cloudy": "облачно с прояснениями",
                 "overcast": "пасмурно",
                 "light-rain": "небольшой дождь", "rain": "дождь", "heavy-rain": "сильный дождь",
                 "showers": 'ливень',
                 "wet-snow": "дождь со снегом", "light-snow": "небольшой снег", "snow": 'снег',
                 "snow-showers": "снегопад",
                 "hail": 'град', "thunderstorm": "гроза", "thunderstorm-with-rain": "дождь с грозой",
                 "thunderstorm-with-hail": "гроза с градом"}
WIND_DIR_RU = {
    'N': 'С',
    'S': 'Ю',
    'W': 'З',
    'E': 'В',
    'NW': 'СЗ',
    'NE': 'СВ',
    'SE': 'ЮВ',
    'SW': 'ЮЗ',
    'C': 'C'
}
TO_WIND_DIR_RU_ENG = {
    'N': 'S',
    'S': 'N',
    'W': 'E',
    'E': 'W',
    'NW': 'SE',
    'NE': 'SW',
    'SE': 'NW',
    'SW': 'NE',
    'С': 'Ю',
    'Ю': 'С',
    'З': 'В',
    'В': 'З',
    'СЗ': 'ЮВ',
    'СВ': 'ЮЗ',
    'ЮВ': 'СЗ',
    'ЮЗ': 'СВ',
    'C': 'штиль',
}
FROM_STATION_INFO = {"image_path": "", 'station': "", "temp": "", "feels_like": "", "icon": "",
                     "condition": "", "wind_speed": "", "pressure_mm": "", "wind_dir_from": "", "wind_dir_to": ""}


async def get_coords_of_object(name_object):
    url = f"https://geocode-maps.yandex.ru/1.x/?apikey={API_GEOCODE_MAPS}&geocode={name_object}&format=json"
    async with ClientSession() as session:
        async with session.get(url) as response:
            response_json = await response.json()
            pos = response_json["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["Point"]["pos"]
            lon, lat = pos.split(" ")
            return lat, lon


async def get_weather(name_object):
    coords = await get_coords_of_object(name_object=name_object)
    units = "metric"
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={coords[0]}&lon={coords[1]}&units={units}&appid={API_WEATHER}"
    headers = {'X-Yandex-API-Key': API_WEATHER}
    async with ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            data = await response.json()
            with open("sample.json", "w") as outfile:
                outfile.write(json.dumps(data))
            return dict(data)


async def asnc_stations_data(stations):
    tasks = []
    for station in stations:
        tasks.append(asyncio.create_task(get_weather(station)))
    results = await asyncio.gather(*tasks)
    return results


# TODO: доделать
@app.route('/list_stations/<line_name>')
def show_line_info(line_name):
    conn = sqlite3.connect('db/Railway_data.db')
    cursor = conn.cursor()
    stations = cursor.execute(f"""SELECT STATIONS FROM LINES WHERE NAME="{line_name}" """).fetchone()[0].split(', ')
    conn.close()
    stations_data = asyncio.run(asnc_stations_data(stations))
    print(stations_data)
    new_form_stations_data = []

    for index, weather_data in enumerate(stations_data):
        image_path = f"/static/img/stations/станция_{stations[index]}.jpg".replace('%20', ' ')
        temperature = int(weather_data["main"]['temp'])  # температура
        feels_like = int(weather_data["main"]["feels_like"])  # ощущается как
        icon = weather_data["weather"]["weather_icon"]  # картинка погоды: требуется доработка
        condition = CONDITIONS_RU[weather_data["condition"]]  # погодное условие: необходимо сверить с html файлом
        wind_speed = weather_data['wind_speed']  # скорость ветра
        pressure_mm = weather_data['pressure_mm']  # давление в мм. рт. ст.
        wind_dir_from = WIND_DIR_RU[weather_data['wind_dir'].upper()]  # направление ветра откуда*
        wind_dir_to = TO_WIND_DIR_RU_ENG[WIND_DIR_RU[weather_data['wind_dir'].upper()]]  # направление ветра куда*

        # делаем форму
        added_form = FROM_STATION_INFO.copy()
        added_form['image_path'] = image_path
        added_form['station'] = stations[index]
        added_form['temp'] = temperature
        added_form['feels_like'] = feels_like
        added_form["icon"] = icon
        added_form["condition"] = condition
        added_form["wind_speed"] = wind_speed
        added_form['pressure_mm'] = pressure_mm
        added_form['wind_dir_from'] = wind_dir_from
        added_form['wind_dir_to'] = wind_dir_to
        new_form_stations_data.append(added_form)

    return render_template('list_stations.html', **CONST_PARAMS, title=line_name,
                           line_name=line_name, stations=stations, stations_data=new_form_stations_data)


def maker_money_beautiful_format(number):
    # красивый ответ -> ans
    ans = ""
    for i in range(len(str(number)[::-1])):
        ans += str(number)[::-1][i]
        if i != 0 and (i + 1) % 3 == 0 and i != len(str(number)[::-1]) - 1:
            ans += '.'
    # возвращаем развернутый ans
    return ans[::-1]


# TODO: доделать обновление кол-ва денег в sql таблице
def update_money():
    CONST_PARAMS['money'] = company.money_beautiful_format()


class Company:
    def __init__(self):
        self.cur = sqlite3.connect('db/Railway_data.db').cursor()
        self.money = int(self.cur.execute(f"""SELECT cash FROM money WHERE id = 1""").fetchall()[0][0])

    def money_beautiful_format(self):
        # красивый ответ -> ans
        ans = ""
        for i in range(len(str(self.money)[::-1])):
            ans += str(self.money)[::-1][i]
            if i != 0 and (i + 1) % 3 == 0 and i != len(str(self.money)[::-1]) - 1:
                ans += '.'
        # возвращаем развернутый ans
        return ans[::-1] + '$'


@app.route('/')
def main_page():
    return render_template('main_page.html', **CONST_PARAMS, title='Главная')


@app.route('/list_stations')
def list_stations():
    db_sess = db_session.create_session()
    stations_data = db_sess.query(Lines)
    conn = sqlite3.connect('db/Railway_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM lines')
    lines = cursor.fetchall()
    conn.close()
    return render_template('list_stations.html', **CONST_PARAMS, title='Список станций',
                           stations_data=stations_data, lines=lines)


@app.route('/list_trains')
def list_trains():
    # buying_info = [i[0] for i in cursor_sql1.execute('SELECT * FROM TRAINS').fetchall()]
    # print(buying_info)
    db_sess = db_session.create_session()
    buying_info = db_sess.query(Trains)
    if current_user.is_authenticated:
        is_authenticated = True
    else:
        is_authenticated = False
    return render_template('list_trains.html', **CONST_PARAMS, buying_info=buying_info,
                           is_authenticated=is_authenticated, title='Список поездов')


@app.route('/scheme')
def scheme():
    return render_template('scheme.html', **CONST_PARAMS, title='Схема')


@app.route("/load_news_by_txt", methods=['GET', 'POST'])
def load_news_by_txt():
    if request.method == "GET":
        return render_template('load_news_by_txt.html', **CONST_PARAMS, title='Загрузка новостей')
    else:
        file = request.files['file']
        if file:
            file.save(os.path.join('uploads', file.filename))
            with open(os.path.join('uploads', file.filename), mode='r', encoding='utf-8') as f:
                content = [i.rstrip() for i in f.readlines()]
                pustishka = False
                if len(content) >= 3:
                    if content[1].lower() in ('true', '0', '1', 'false'):
                        db_sess = db_session.create_session()
                        news = News()
                        news.title = content[0].lower().capitalize()  # str
                        news.content = "\n".join(content[2:])  # str
                        # bool
                        if content[1].lower() in ('true', '1'):
                            news.is_private = True
                        else:
                            news.is_private = False
                        current_user.news.append(news)
                        db_sess.merge(current_user)
                        db_sess.commit()
                    else:
                        pustishka = True
                else:
                    pustishka = True

                if pustishka:
                    db_sess = db_session.create_session()
                    news = News()
                    news.title = "Странная новость..."  # str
                    st_temp = """Была добавлена странная новость, которая как-то перекочевала из текстого 
                                    файла. Увы. \n Странные новости появляются, когда что-то идёт не так. \n 
                                    Смотрите правила отправки в форме..."""
                    news.content = st_temp  # str
                    news.is_private = True  # bool
                    current_user.news.append(news)
                    db_sess.merge(current_user)
                    db_sess.commit()

                # на случай тестирования
                # for line in content:
                #     print(line)
            os.remove(os.path.join('uploads', file.filename))
            return redirect('/news')


@app.route('/train_info')
def train_info():
    if current_user.is_authenticated:
        is_authenticated = True
    else:
        is_authenticated = False
    return render_template('train_info.html', **CONST_PARAMS, is_authenticated=is_authenticated,
                           lastochka_places=LASTOCHKA_PLACES,
                           ivolga_places=IVOLGA_PLACES, title='Характеристика поездов',
                           locomotive_lifting_capacity=LOCOMOTIVE_LIFTIONG_CAPACITY)


@app.route('/resources')
def resources():
    if current_user.is_authenticated:
        is_authenticated = True
    else:
        is_authenticated = False
    return render_template('resources.html', **CONST_PARAMS, resources=RESOURCES,
                           is_authenticated=is_authenticated, title='Виды ресурсов')


@app.route('/buying_train', methods=['GET', "POST"])
def buying_train():
    if current_user.is_authenticated:
        is_authenticated = True
    else:
        is_authenticated = False

    if request.method == 'GET':
        params = {"lines": LINES, "line_to_stations": dic_line_to_stations}
        return render_template('buying_train.html', **params, **CONST_PARAMS,
                               is_authenticated=is_authenticated, title='Покупка поезда')
    elif request.method == 'POST':
        params = dict(request.form)
        train_type = params['train_type']
        conn1 = sqlite3.connect('db/Railway_data.db')
        cur = conn1.cursor()
        # Заметка: переводим тип поезда в кириллицу
        if train_type == 'express':
            company.money -= LASTOCHKA_PRICE
            train_type = 'Экспресс'
        elif train_type == 'local':
            company.money -= IVOLGA_PRICE
            train_type = 'Пригородный'
        else:
            company.money -= LOCOMOTIVE_PRICE
            train_type = 'Грузовой'

        cur.execute(f"""UPDATE money
                        SET cash = {company.money}
                        WHERE id = 1""")
        conn1.commit()
        update_money()
        # имя поезда, пробел, № id
        line = params['line']
        station1 = params['station1']
        station2 = params['station2']
        trip_cost = params['trip_cost']
        cur.execute(f"""INSERT INTO trains(name, station1, station2, price, line_id)
                        VALUES('{train_type} №{line}', '{station1}', '{station2}', {trip_cost}, '{line}')""")
        conn1.commit()
        return render_template('result_buying_train.html', train_type=train_type, line=line,
                               station1=station1, **CONST_PARAMS, title='Покупка поезда',
                               station2=station2, trip_cost=trip_cost)


@app.route
@login_manager.user_loader
def load_user(user_id):
    db_sess = db_session.create_session()
    return db_sess.query(User).get(user_id)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect("/")


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        user = db_sess.query(User).filter(User.email == form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            return redirect("/")
        return render_template('login.html', **CONST_PARAMS,
                               message="Неправильный логин или пароль",
                               form=form, title=":(")
    return render_template('login.html', title='Авторизация', form=form, **CONST_PARAMS)


@app.route("/news")
def news():
    db_sess = db_session.create_session()
    if current_user.is_authenticated:
        news = db_sess.query(News).filter((News.user == current_user) | (News.is_private == 0))
    else:
        news = db_sess.query(News).filter(News.is_private != 1)
    return render_template("news.html", **CONST_PARAMS, news=news, title='Новости')


@app.route('/add_news', methods=['GET', 'POST'])
@login_required
def add_news():
    form = NewsForm()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        news = News()
        news.title = form.title.data  # str
        news.content = form.content.data  # str
        news.is_private = form.is_private.data  # bool
        current_user.news.append(news)
        db_sess.merge(current_user)
        db_sess.commit()
        return redirect('/news')
    return render_template('add_news.html', title='Добавление новости', **CONST_PARAMS,
                           form=form)


@app.route('/edit_news/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_news(id):
    form = NewsForm()
    if request.method == "GET":
        db_sess = db_session.create_session()
        news = db_sess.query(News).filter(News.id == id,
                                          News.user == current_user
                                          ).first()
        if news:
            form.title.data = news.title
            form.content.data = news.content
            form.is_private.data = news.is_private
        else:
            abort(404)
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        news = db_sess.query(News).filter(News.id == id,
                                          News.user == current_user
                                          ).first()
        if news:
            news.title = form.title.data
            news.content = form.content.data
            news.is_private = form.is_private.data
            db_sess.commit()
            return redirect('/news')
        else:
            abort(404)
    return render_template('add_news.html', **CONST_PARAMS,
                           title='Редактирование новости',
                           form=form)


@app.route('/news_delete/<int:id>', methods=['GET', 'POST'])
@login_required
def news_delete(id):
    db_sess = db_session.create_session()
    news = db_sess.query(News).filter(News.id == id, News.user_id != 7,
                                      News.user == current_user
                                      ).first()
    if news:
        db_sess.delete(news)
        db_sess.commit()
    else:
        # abort(404)
        return redirect('/news')
    return redirect('/news')


@app.route('/register', methods=['GET', 'POST'])
def reqister():
    form = RegisterForm()
    if form.validate_on_submit():
        if form.password.data != form.password_again.data:
            return render_template('register.html', title='Регистрация',
                                   form=form, **CONST_PARAMS,
                                   message="Пароли не совпадают")
        db_sess = db_session.create_session()
        if db_sess.query(User).filter(User.email == form.email.data).first():
            return render_template('register.html', title='Регистрация',
                                   form=form, **CONST_PARAMS,
                                   message="Такой пользователь уже есть")
        user = User(
            name=form.name.data,
            email=form.email.data,
            about=form.about.data
        )
        user.set_password(form.password.data)
        db_sess.add(user)
        db_sess.commit()
        return redirect('/login')
    return render_template('register.html', title='Регистрация', form=form, **CONST_PARAMS)


@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)


@app.errorhandler(400)
def bad_request(_):
    return make_response(jsonify({'error': 'Bad Request'}), 400)


def new_update_money():
    while True:
        con1 = sqlite3.connect('db/Railway_data.db')
        cursor_sql1 = con1.cursor()
        trains = len(cursor_sql1.execute("SELECT NAME FROM TRAINS").fetchall())
        company.money += sum([random.randint(50, 230) for _ in range(trains)])
        update_money()
        time.sleep(3)


def main():
    db_session.global_init("db/Railway_data.db")

    app.register_blueprint(news_api.blueprint)
    # для списка объектов
    api.add_resource(news_resources.NewsListResource, '/api/v2/news')

    # для одного объекта
    api.add_resource(news_resources.NewsResource, '/api/v2/news/<int:news_id>')

    t = Thread(target=new_update_money)
    t.start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)


company = Company()

con1 = sqlite3.connect('db/Railway_data.db')
cursor_sql1 = con1.cursor()

LINES = [i[0] for i in cursor_sql1.execute('SELECT name FROM LINES').fetchall()]
dic_line_to_stations = {i[0]: i[1].split(', ') for i in
                        cursor_sql1.execute('SELECT name, stations FROM LINES').fetchall()}

RESOURCES = ['Нефтепродукты', "Строительные материалы", "Химическая продукция", "Металлопрокат",
             "Контейнеры", "Уголь", "Нефть", "Песок", "Глина", "Древесина", "Сталь", "Алюминий", "Зерно", "Сахар",
             "Мука", "Фрукты", "Овощи", "Мясо", "Рыба", "Молоко",
             "Яйца", "Ткани", "Одежда", "Обувь", "Мебель", "Электроника", "Автомобили",
             "Мотоциклы", "Книги", "Бумага", "Пластик", "Стекло", "Керамика",
             "Лекарства", "Химикаты"]
# ресурсы и вес единицы этого ресурса в кг || ВРЯД ЛИ ЭТО ПРИГОДИТСЯ
resources_weight = {
    'Нефтепродукты': 500, "Строительные материалы": 1000, "Химическая продукция": 300, "Металлопрокат": 700,
    "Контейнеры": 200, "Уголь": 600, "Нефть": 800, "Песок": 1200, "Глина": 1000,
    "Древесина": 500, "Сталь": 900, "Алюминий": 400, "Зерно": 600, "Сахар": 300,
    "Мука": 400, "Фрукты": 200, "Овощи": 300, "Мясо": 500, "Рыба": 400, "Молоко": 1000, "Яйца": 200, "Ткани": 300,
    "Одежда": 500, "Обувь": 400, "Мебель": 600, "Электроника": 200, "Автомобили": 1500, "Мотоциклы": 300,
    "Книги": 200, "Бумага": 400, "Пластик": 500, "Стекло": 700, "Керамика": 600, "Лекарства": 300, "Химикаты": 400}

# цены в $
LASTOCHKA_PRICE = 65000
IVOLGA_PRICE = 85000
LOCOMOTIVE_PRICE = 60000
# вместимость в кол-ве людей
LASTOCHKA_PLACES = 1100
IVOLGA_PLACES = 2550
# вместимость в вагонах
LOCOMOTIVE_LIFTIONG_CAPACITY = 20
CONST_PARAMS = {'money': company.money_beautiful_format(),
                'lastochka_price': maker_money_beautiful_format(LASTOCHKA_PRICE),
                'ivolga_price': maker_money_beautiful_format(IVOLGA_PRICE),
                'locomotive_price': maker_money_beautiful_format(LOCOMOTIVE_PRICE)}

if __name__ == '__main__':
    main()
