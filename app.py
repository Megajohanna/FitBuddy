from flask import Flask, render_template, request

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def home():
    plan = None

    if request.method == "POST":
        name = request.form.get("name")
        age = request.form.get("age")
        goal = request.form.get("goal")
        level = request.form.get("level")

        if goal == "Weight Loss":
            workout = "Walking, jogging and light cardio"
            food = "Balanced meals with vegetables, fruits and adequate protein"

        elif goal == "Muscle Gain":
            workout = "Strength training and bodyweight exercises"
            food = "Balanced meals with protein-rich foods"

        else:
            workout = "Walking, stretching and basic exercises"
            food = "A balanced and varied diet"

        plan = {
            "name": name,
            "age": age,
            "goal": goal,
            "level": level,
            "workout": workout,
            "food": food
        }

    return render_template("index.html", plan=plan)


if __name__ == "__main__":
    app.run(debug=True)
