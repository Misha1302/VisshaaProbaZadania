import datetime
from typing import List

from flask import *

app = Flask(__name__)


class Plant:
    def __init__(self, id, interval, max_delay, date):
        self.id = id
        self.interval = interval
        self.max_delay = max_delay
        self.current_date = date

    def do_next_step(self, new_date):
        left_date = self.current_date
        right_date = self.current_date + datetime.timedelta(days=self.max_delay)

        if right_date < new_date:
            return True

        if left_date > new_date:
            return False

        self.current_date = self.current_date + datetime.timedelta(days=self.interval)
        return False

    def need_to_delete(self, new_date):
        left_date = self.current_date
        right_date = self.current_date + datetime.timedelta(days=self.max_delay)
        return right_date < new_date

    def need_to_water(self, new_date):
        left_date = self.current_date
        right_date = self.current_date + datetime.timedelta(days=self.max_delay)

        return left_date <= new_date <= right_date


plants: List[Plant] = []


def remove_old(date):
    plants_to_remove = []
    for p in plants:
        if p.need_to_delete(date):
            plants_to_remove.append(p)

    for p in plants_to_remove:
        plants.remove(p)


@app.route('/add/<plant>/<int:interval>/<int:maxdelay>/', methods=['GET'])
def add_plant(plant: str, interval: int, maxdelay: int):
    arg_str = request.args['date']
    date = datetime.datetime.strptime(arg_str, "%d.%m.%Y")

    plants.append(Plant(plant, interval, maxdelay, date))
    remove_old(date)

    return "OK", 200


@app.route('/task/', methods=['GET'])
def who_need_to_water():
    date = datetime.datetime.strptime(request.args['date'], "%d.%m.%Y")

    remove_old(date)

    answer = []
    for plant in plants:
        if plant.need_to_water(date):
            answer.append(plant.id)

    ans = ",".join(answer)
    print(ans)
    return ans


@app.route('/watering/<plant>/', methods=['GET'])
def do_water(plant: str):
    date = datetime.datetime.strptime(request.args['date'], "%d.%m.%Y")

    remove_old(date)

    for p in plants:
        if p.id == plant and p.need_to_water(date):
            p.do_next_step(date)

    return "OK", 200


app.run(debug=True, host='127.0.0.1', port=8080)
