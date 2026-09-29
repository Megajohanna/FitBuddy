"""
FitBuddy - Your AI Personal Fitness & Nutrition Coach
Flask Web Application
"""

import os
import json
import logging
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fitbuddy")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fitbuddy-fallback-secret-2026")

# Check Gemini API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Initialize Gemini Client if available
gemini_client = None
if GEMINI_API_KEY:
    try:
        from google import genai
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("FitBuddy: Gemini AI client successfully initialized.")
    except Exception as e:
        logger.warning(f"FitBuddy: Could not initialize Gemini client: {e}. Running in smart rule engine mode.")
else:
    logger.info("FitBuddy: GEMINI_API_KEY is not set. Running with built-in smart fitness rule engine.")


# ==========================================
# HEALTH & FITNESS CALCULATION LOGIC
# ==========================================

def compute_fitness_metrics(age, gender, weight_kg, height_cm, activity_level, goal, dietary_pref="omnivore"):
    """
    Computes BMI, BMR (Mifflin-St Jeor), TDEE, Caloric Targets, Macros, and Water Intake.
    """
    # 1. BMI Calculation
    height_m = height_cm / 100.0
    bmi = round(weight_kg / (height_m ** 2), 1)
    
    if bmi < 18.5:
        bmi_category = "Underweight"
        bmi_color = "text-blue-500"
        bmi_advice = "Focus on a nutrient-dense caloric surplus and progressive resistance training to build healthy mass."
    elif 18.5 <= bmi < 25.0:
        bmi_category = "Normal weight"
        bmi_color = "text-emerald-500"
        bmi_advice = "Great job! Maintain your balanced nutritional habits and focus on strength and endurance development."
    elif 25.0 <= bmi < 30.0:
        bmi_category = "Overweight"
        bmi_color = "text-amber-500"
        bmi_advice = "A moderate caloric deficit paired with consistent cardiovascular and resistance workouts will yield great results."
    else:
        bmi_category = "Obese"
        bmi_color = "text-rose-500"
        bmi_advice = "Prioritize sustainable daily habits: whole foods, hydration, and low-impact daily movement like brisk walking."

    # Healthy Weight Range for height (BMI 18.5 - 24.9)
    min_healthy_weight = round(18.5 * (height_m ** 2), 1)
    max_healthy_weight = round(24.9 * (height_m ** 2), 1)

    # 2. BMR - Mifflin-St Jeor Equation
    # Men: BMR = 10W + 6.25H - 5A + 5
    # Women: BMR = 10W + 6.25H - 5A - 161
    if gender.lower() == "male":
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5
    elif gender.lower() == "female":
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161
    else:
        # Non-binary / default average
        bmr_m = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5
        bmr_f = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161
        bmr = (bmr_m + bmr_f) / 2
    bmr = round(bmr)

    # 3. TDEE (Total Daily Energy Expenditure)
    activity_multipliers = {
        "sedentary": 1.2,       # Little or no exercise, desk job
        "light": 1.375,         # Light exercise 1-3 days/week
        "moderate": 1.55,       # Moderate exercise 3-5 days/week
        "active": 1.725,        # Heavy exercise 6-7 days/week
        "extra_active": 1.9     # Very heavy exercise / physical job
    }
    multiplier = activity_multipliers.get(activity_level, 1.2)
    tdee = round(bmr * multiplier)

    # 4. Target Calories based on Goal
    if goal == "weight_loss":
        target_calories = max(1200, tdee - 500)
        calorie_notes = "500 kcal deficit for a safe, steady fat loss rate (~0.5 kg / 1 lb per week)."
    elif goal == "extreme_loss":
        target_calories = max(1200, tdee - 750)
        calorie_notes = "Aggressive 750 kcal deficit. Ensure high protein intake to preserve lean muscle."
    elif goal == "muscle_gain":
        target_calories = tdee + 350
        calorie_notes = "Controlled 350 kcal surplus (lean bulk) to maximize muscle hypertrophy while minimizing fat accumulation."
    elif goal == "endurance":
        target_calories = tdee + 200
        calorie_notes = "High-energy baseline tailored to support glycogen replenishment and workout endurance."
    else:  # "maintenance" or "general_fitness"
        target_calories = tdee
        calorie_notes = "Maintenance calories to fuel daily activities and sustain current weight."

    # 5. Macronutrient Distribution
    # Grams: Protein = 4 kcal/g, Carbs = 4 kcal/g, Fat = 9 kcal/g
    if dietary_pref == "keto":
        protein_pct = 0.25
        fat_pct = 0.70
        carbs_pct = 0.05
    elif goal in ["weight_loss", "extreme_loss"]:
        protein_pct = 0.35  # High protein to spare muscle
        fat_pct = 0.25
        carbs_pct = 0.40
    elif goal == "muscle_gain":
        protein_pct = 0.30
        fat_pct = 0.25
        carbs_pct = 0.45
    elif goal == "endurance":
        protein_pct = 0.20
        fat_pct = 0.25
        carbs_pct = 0.55  # Fuel long training sessions
    else:
        protein_pct = 0.25
        fat_pct = 0.30
        carbs_pct = 0.45

    protein_kcal = target_calories * protein_pct
    fat_kcal = target_calories * fat_pct
    carbs_kcal = target_calories * carbs_pct

    protein_g = round(protein_kcal / 4)
    fat_g = round(fat_kcal / 9)
    carbs_g = round(carbs_kcal / 4)

    # 6. Daily Water Intake (in Liters and Glasses)
    # Approx 33ml per kg body weight + extra for activity
    activity_water_bonus = {
        "sedentary": 0.0,
        "light": 0.3,
        "moderate": 0.5,
        "active": 0.8,
        "extra_active": 1.0
    }
    water_liters = round((weight_kg * 0.033) + activity_water_bonus.get(activity_level, 0.3), 1)
    water_glasses = round((water_liters * 1000) / 250)  # standard 250ml glass

    return {
        "bmi": bmi,
        "bmi_category": bmi_category,
        "bmi_color": bmi_color,
        "bmi_advice": bmi_advice,
        "healthy_weight_range": f"{min_healthy_weight} - {max_healthy_weight} kg",
        "bmr": bmr,
        "tdee": tdee,
        "target_calories": target_calories,
        "calorie_notes": calorie_notes,
        "macros": {
            "protein": {"grams": protein_g, "calories": round(protein_kcal), "percent": int(protein_pct * 100)},
            "carbs": {"grams": carbs_g, "calories": round(carbs_kcal), "percent": int(carbs_pct * 100)},
            "fat": {"grams": fat_g, "calories": round(fat_kcal), "percent": int(fat_pct * 100)}
        },
        "water": {
            "liters": water_liters,
            "glasses": water_glasses
        }
    }


# ==========================================
# BUILT-IN SMART RULE-BASED PLAN ENGINE
# (Offline & Fallback when Gemini key is not set)
# ==========================================

def generate_fallback_workout_and_diet(data):
    """
    Generates a structured, highly personalized 7-day workout schedule and meal plan
    without requiring an external API call.
    """
    goal = data.get("goal", "general_fitness")
    level = data.get("level", "intermediate")
    equipment = data.get("equipment", "full_gym")
    days_per_week = int(data.get("days_per_week", 4))
    dietary_pref = data.get("dietary_pref", "omnivore")
    calories = data.get("calories", 2000)
    injuries = data.get("injuries", "").strip()

    # Determine split template based on days per week
    if days_per_week <= 3:
        routine_type = "Full Body Circuit (3 Days)"
        days_structure = [
            ("Day 1: Full Body Strength A", "Compound Push, Pull, and Leg foundations"),
            ("Day 2: Active Recovery & Mobility", "Light walking, dynamic stretches, foam rolling"),
            ("Day 3: Full Body Strength B", "Posterior chain, overhead press, core stabilization"),
            ("Day 4: Rest & Hydration", "Complete rest and muscle recovery"),
            ("Day 5: Full Body Functional & Core", "Unilateral movements, core conditioning"),
            ("Day 6: Low Impact Cardio / Outdoor Walk", "30-45 min Zone 2 aerobic activity"),
            ("Day 7: Rest & Weekly Meal Prep", "Recharge and prep nutritious meals for the week")
        ]
    elif days_per_week == 4:
        routine_type = "Upper / Lower Split (4 Days)"
        days_structure = [
            ("Day 1: Upper Body Power", "Chest, Back, Shoulders, and Arms"),
            ("Day 2: Lower Body Power", "Quads, Hamstrings, Glutes, and Calves"),
            ("Day 3: Active Rest & Recovery", "Mobility routine and light walking"),
            ("Day 4: Upper Body Hypertrophy", "High-volume pumps and arm focus"),
            ("Day 5: Lower Body & Abs Hypertrophy", "Leg press/squat variations, calves, core"),
            ("Day 6: Cardio & Core Conditioning", "20-30 min HIIT or steady state cardio"),
            ("Day 7: Full Rest & Recovery", "Mental recharge, foam rolling, hydration")
        ]
    elif days_per_week == 5:
        routine_type = "Push / Pull / Legs / Upper / Lower (5 Days)"
        days_structure = [
            ("Day 1: Push Day", "Chest, Front/Lateral Deltoids, Triceps"),
            ("Day 2: Pull Day", "Back, Rear Delts, Biceps, Forearms"),
            ("Day 3: Legs & Core", "Squat patterns, RDL, Calves, Hanging knee raises"),
            ("Day 4: Rest Day", "Light mobility and hydration focus"),
            ("Day 5: Upper Body Sculpt", "Incline presses, rows, supersets"),
            ("Day 6: Lower Body & Glutes", "Hip thrusts, lunges, leg curls"),
            ("Day 7: Rest & Recovery", "Sleep optimization and nutrition prep")
        ]
    else: # 6 days
        routine_type = "Push / Pull / Legs x2 Split (6 Days)"
        days_structure = [
            ("Day 1: Push (Heavy)", "Bench press, Overhead press, Dips, Lateral raises"),
            ("Day 2: Pull (Heavy)", "Barbell rows, Pull-ups/Lat pulldowns, Bicep curls"),
            ("Day 3: Legs (Heavy)", "Barbell squats, Romanian deadlifts, Calf raises"),
            ("Day 4: Push (Hypertrophy)", "Dumbbell presses, Incline flyes, Skull crushers"),
            ("Day 5: Pull (Hypertrophy)", "Cable rows, Face pulls, Hammer curls, Shrugs"),
            ("Day 6: Legs (Hypertrophy)", "Leg press, Bulgarian split squats, Leg curls"),
            ("Day 7: Complete Rest", "Refuel, relax, sleep minimum 8 hours")
        ]

    # Exercise database variations based on equipment
    exercises_db = {
        "full_gym": {
            "chest": [("Barbell Bench Press", "4 sets x 8-10 reps", "90s rest"), ("Incline Dumbbell Press", "3 sets x 10-12 reps", "60s rest"), ("Cable Chest Flyes", "3 sets x 15 reps", "45s rest")],
            "back": [("Bent-Over Barbell Rows", "4 sets x 8-10 reps", "90s rest"), ("Lat Pulldowns", "3 sets x 10-12 reps", "60s rest"), ("Seated Cable Rows", "3 sets x 12 reps", "60s rest")],
            "legs": [("Barbell Back Squats", "4 sets x 8-10 reps", "120s rest"), ("Romanian Deadlifts (RDL)", "3 sets x 10-12 reps", "90s rest"), ("Leg Extensions & Curls", "3 sets x 15 reps", "60s rest")],
            "shoulders": [("Standing Overhead Press", "4 sets x 8 reps", "90s rest"), ("Dumbbell Lateral Raises", "4 sets x 15 reps", "45s rest"), ("Face Pulls", "3 sets x 15 reps", "45s rest")],
            "arms": [("Barbell Bicep Curls", "3 sets x 12 reps", "45s rest"), ("Tricep Rope Pushdowns", "3 sets x 12 reps", "45s rest")],
            "core": [("Hanging Leg Raises", "3 sets x 12 reps", "45s rest"), ("Cable Woodchoppers", "3 sets x 15 reps/side", "45s rest")]
        },
        "dumbbells_bands": {
            "chest": [("Dumbbell Floor/Bench Press", "4 sets x 10-12 reps", "60s rest"), ("Dumbbell Push-Ups", "3 sets to failure", "60s rest"), ("Resistance Band Flyes", "3 sets x 15 reps", "45s rest")],
            "back": [("Dumbbell Single-Arm Rows", "4 sets x 10-12 reps/side", "60s rest"), ("Resistance Band Pull-Aparts", "3 sets x 20 reps", "45s rest"), ("Dumbbell Pullovers", "3 sets x 12 reps", "60s rest")],
            "legs": [("Dumbbell Goblet Squats", "4 sets x 12 reps", "90s rest"), ("Dumbbell Romanian Deadlifts", "4 sets x 12 reps", "90s rest"), ("Dumbbell Walking Lunges", "3 sets x 12 reps/leg", "60s rest")],
            "shoulders": [("Dumbbell Arnold Press", "3 sets x 10 reps", "60s rest"), ("Dumbbell Lateral Raises", "4 sets x 15 reps", "45s rest"), ("Band Face Pulls", "3 sets x 20 reps", "45s rest")],
            "arms": [("Dumbbell Hammer Curls", "3 sets x 12 reps", "45s rest"), ("Overhead Dumbbell Extension", "3 sets x 12 reps", "45s rest")],
            "core": [("Plank with Shoulder Taps", "3 sets x 40 seconds", "45s rest"), ("Russian Twists with Dumbbell", "3 sets x 20 reps", "45s rest")]
        },
        "bodyweight_only": {
            "chest": [("Standard Push-Ups", "4 sets x 12-15 reps", "60s rest"), ("Diamond Push-Ups", "3 sets x 8-10 reps", "60s rest"), ("Decline Push-Ups (feet on chair)", "3 sets x 10-12 reps", "60s rest")],
            "back": [("Inverted Rows (under table or bar)", "4 sets x 10-12 reps", "60s rest"), ("Prone Back Supermans", "3 sets x 15 reps", "45s rest"), ("Doorway Rows", "3 sets x 15 reps", "45s rest")],
            "legs": [("Bodyweight Squats (slow tempo)", "4 sets x 20 reps", "60s rest"), ("Walking Lunges", "3 sets x 15 reps/leg", "60s rest"), ("Single-Leg Glute Bridges", "3 sets x 12 reps/leg", "45s rest")],
            "shoulders": [("Pike Push-Ups", "3 sets x 8-10 reps", "60s rest"), ("Prone Y-T-W Raises", "3 sets x 12 reps each", "45s rest")],
            "arms": [("Bench / Chair Dips", "3 sets x 12-15 reps", "45s rest"), ("Towel Bicep Isometric Curls", "3 sets x 30s tension", "45s rest")],
            "core": [("Hollow Body Hold", "3 sets x 30-45 seconds", "45s rest"), ("Bicycle Crunches", "3 sets x 20 reps", "45s rest"), ("Side Planks", "3 sets x 30s/side", "45s rest")]
        }
    }

    selected_db = exercises_db.get(equipment, exercises_db["full_gym"])

    # Build 7-day schedule
    schedule = []
    for day_title, day_desc in days_structure:
        if "Rest" in day_title or "Recovery" in day_title:
            exercises = [
                {"name": "Light Walking or Cycling", "sets_reps": "20-30 minutes", "rest": "Zone 1-2 effort", "notes": "Promotes active blood circulation and faster recovery."},
                {"name": "Full Body Mobility & Stretching", "sets_reps": "15 minutes", "rest": "Deep diaphragmatic breathing", "notes": "Focus on hips, hamstrings, thoracic spine, and chest opening."}
            ]
        elif "Push" in day_title or "Chest" in day_title:
            exercises = [
                {"name": selected_db["chest"][0][0], "sets_reps": selected_db["chest"][0][1], "rest": selected_db["chest"][0][2], "notes": "Control the descent (3 sec negative) and explode up."},
                {"name": selected_db["chest"][1][0], "sets_reps": selected_db["chest"][1][1], "rest": selected_db["chest"][1][2], "notes": "Squeeze the chest at peak contraction."},
                {"name": selected_db["shoulders"][0][0], "sets_reps": selected_db["shoulders"][0][1], "rest": selected_db["shoulders"][0][2], "notes": "Maintain braced core; do not arch lower back."},
                {"name": selected_db["shoulders"][1][0], "sets_reps": selected_db["shoulders"][1][1], "rest": selected_db["shoulders"][1][2], "notes": "Lead with elbows for optimal deltoid isolation."},
                {"name": selected_db["arms"][1][0], "sets_reps": selected_db["arms"][1][1], "rest": selected_db["arms"][1][2], "notes": "Lock out triceps at bottom."}
            ]
        elif "Pull" in day_title or "Back" in day_title:
            exercises = [
                {"name": selected_db["back"][0][0], "sets_reps": selected_db["back"][0][1], "rest": selected_db["back"][0][2], "notes": "Drive elbows back and retract shoulder blades."},
                {"name": selected_db["back"][1][0], "sets_reps": selected_db["back"][1][1], "rest": selected_db["back"][1][2], "notes": "Full stretch at top; pull to upper chest."},
                {"name": selected_db["shoulders"][2][0], "sets_reps": selected_db["shoulders"][2][1], "rest": selected_db["shoulders"][2][2], "notes": "Essential for posture and shoulder health."},
                {"name": selected_db["arms"][0][0], "sets_reps": selected_db["arms"][0][1], "rest": selected_db["arms"][0][2], "notes": "Strict form without swinging momentum."}
            ]
        elif "Legs" in day_title or "Lower" in day_title:
            exercises = [
                {"name": selected_db["legs"][0][0], "sets_reps": selected_db["legs"][0][1], "rest": selected_db["legs"][0][2], "notes": "Knees track over toes; hit at least parallel depth."},
                {"name": selected_db["legs"][1][0], "sets_reps": selected_db["legs"][1][1], "rest": selected_db["legs"][1][2], "notes": "Hinge at hips; feel deep hamstring stretch."},
                {"name": selected_db["legs"][2][0], "sets_reps": selected_db["legs"][2][1], "rest": selected_db["legs"][2][2], "notes": "Smooth controlled repetitions."},
                {"name": selected_db["core"][0][0], "sets_reps": selected_db["core"][0][1], "rest": selected_db["core"][0][2], "notes": "Control swing; engage lower abdominals."}
            ]
        else: # Full body or Upper
            exercises = [
                {"name": selected_db["legs"][0][0], "sets_reps": selected_db["legs"][0][1], "rest": selected_db["legs"][0][2], "notes": "Core braced."},
                {"name": selected_db["chest"][0][0], "sets_reps": selected_db["chest"][0][1], "rest": selected_db["chest"][0][2], "notes": "Chest active."},
                {"name": selected_db["back"][0][0], "sets_reps": selected_db["back"][0][1], "rest": selected_db["back"][0][2], "notes": "Retract scapulae."},
                {"name": selected_db["core"][1][0], "sets_reps": selected_db["core"][1][1], "rest": selected_db["core"][1][2], "notes": "Controlled twisting rotation."}
            ]

        # Add injury modifications if provided
        if injuries:
            exercises.append({
                "name": "Customized Rehabilitation & Caution Note",
                "sets_reps": "Ongoing",
                "rest": "As needed",
                "notes": f"Exercise caution with reported limitation ({injuries}). Always warm up thoroughly and cease any movement causing sharp discomfort."
            })

        schedule.append({
            "day": day_title,
            "focus": day_desc,
            "exercises": exercises
        })

    # Meal Plan based on dietary preferences
    diet_templates = {
        "omnivore": {
            "breakfast": "Scrambled eggs (3 large) with baby spinach, whole grain sourdough toast, and half an avocado.",
            "lunch": "Grilled chicken breast (180g) with quinoa, roasted Mediterranean vegetables, and extra virgin olive oil.",
            "dinner": "Pan-seared Atlantic salmon fillet with steamed sweet potato mash and sautéed asparagus or broccoli.",
            "snack": "Greek yogurt (200g) with a handful of blueberries, chia seeds, and a scoop of whey protein or raw almonds."
        },
        "vegetarian": {
            "breakfast": "Rolled oats cooked with soy or almond milk, chia seeds, sliced banana, and whey/pea protein powder.",
            "lunch": "Warm quinoa bowl with grilled spiced paneer or tofu (150g), roasted chickpeas, edamame, and tahini dressing.",
            "dinner": "Hearty lentil and sweet potato dal with brown basmati rice, steamed spinach, and a crisp cucumber salad.",
            "snack": "Cottage cheese (or Greek yogurt) with mixed walnuts, honey, and an apple."
        },
        "vegan": {
            "breakfast": "Tofu scramble with nutritional yeast, bell peppers, turmeric, and avocado on sprouted seeded grain toast.",
            "lunch": "Tempeh and black bean power bowl with quinoa, roasted sweet potatoes, kale, and lemon-tahini drizzle.",
            "dinner": "Chickpea and coconut milk red curry with mixed vegetables, served over brown rice and steamed edamame.",
            "snack": "Plant-based protein shake blended with frozen berries, flaxseed, and peanut butter, plus carrot sticks with hummus."
        },
        "keto": {
            "breakfast": "Omelette with cheddar cheese, smoked bacon or mushrooms, sautéed spinach in grass-fed butter.",
            "lunch": "Caesar salad with grilled chicken thighs, crispy bacon bits, shaved parmesan, avocado, and full-fat olive oil dressing.",
            "dinner": "Grass-fed ribeye steak or salmon with herb butter, served with mashed cauliflower and garlic green beans.",
            "snack": "Macadamia nuts, string cheese, and hard-boiled eggs with sea salt."
        },
        "high_protein": {
            "breakfast": "Egg white & whole egg scramble (4 whites, 2 whole), lean turkey breast, oats with protein powder.",
            "lunch": "Tuna or chicken breast steak (200g) over jasmine rice, steamed broccoli, and avocado slices.",
            "dinner": "Lean ground sirloin beef (93/7) chili with kidney beans, bell peppers, topped with plain Greek yogurt.",
            "snack": "Whey isolate protein shake with rice cakes and almond butter, plus beef biltong or cottage cheese."
        }
    }

    meal_plan = diet_templates.get(dietary_pref, diet_templates["omnivore"])

    return {
        "source": "Smart FitBuddy Engine (Offline Mode)",
        "routine_type": routine_type,
        "fitness_level": level.capitalize(),
        "equipment": equipment.replace("_", " ").title(),
        "dietary_preference": dietary_pref.capitalize(),
        "target_calories": f"{calories} kcal/day",
        "schedule": schedule,
        "nutrition_plan": {
            "overview": f"Balanced {dietary_pref.capitalize()} daily meal structure calibrated for ~{calories} kcal.",
            "breakfast": meal_plan["breakfast"],
            "lunch": meal_plan["lunch"],
            "dinner": meal_plan["dinner"],
            "snack": meal_plan["snack"]
        },
        "coaching_tips": [
            "Progressive Overload: Strive to add 1 repetition or slight resistance increment each week.",
            "Hydration First: Drink 500ml of water immediately upon waking to kickstart metabolic processes.",
            "Sleep & Recovery: Aim for 7.5 to 8.5 hours of quality restorative sleep; muscles grow during recovery, not the gym.",
            "Form Over Weight: Never compromise joint angles or biomechanics for heavier weight."
        ]
    }


# ==========================================
# GEMINI AI POWERED ENGINE
# ==========================================

def generate_ai_fitness_plan_gemini(data):
    """
    Calls the Gemini API (using gemini-3.8-flash) via google-genai SDK to generate
    a deeply customized, elite personal trainer workout & nutrition plan.
    """
    if not gemini_client:
        return generate_fallback_workout_and_diet(data)

    goal = data.get("goal", "general_fitness")
    level = data.get("level", "intermediate")
    equipment = data.get("equipment", "full_gym")
    days_per_week = data.get("days_per_week", 4)
    dietary_pref = data.get("dietary_pref", "omnivore")
    calories = data.get("calories", 2000)
    injuries = data.get("injuries", "None reported")
    age = data.get("age", 28)
    gender = data.get("gender", "neutral")

    prompt = f"""
    You are an elite, certified personal trainer (CSCS) and registered sports dietitian.
    Generate a comprehensive 7-day personalized workout schedule and a tailored daily meal plan.

    USER PROFILE:
    - Age: {age}, Gender: {gender}
    - Primary Goal: {goal}
    - Fitness Experience Level: {level}
    - Equipment Access: {equipment}
    - Training Frequency: {days_per_week} days per week
    - Dietary Preference: {dietary_pref}
    - Daily Target Calories: {calories} kcal
    - Limitations / Injuries: {injuries}

    Provide your response strictly in valid JSON format matching this exact JSON schema:
    {{
        "source": "Gemini 3.8 Flash AI",
        "routine_type": "Specific split name (e.g. Upper/Lower, PPL, etc.)",
        "fitness_level": "{level.capitalize()}",
        "equipment": "{equipment}",
        "dietary_preference": "{dietary_pref}",
        "target_calories": "{calories} kcal/day",
        "schedule": [
            {{
                "day": "Day 1: Title",
                "focus": "Brief focus description",
                "exercises": [
                    {{
                        "name": "Exercise name",
                        "sets_reps": "e.g. 3 sets x 10 reps",
                        "rest": "e.g. 60s",
                        "notes": "Coaching cue for technique and safety"
                    }}
                ]
            }}
            // ... include all 7 days (Day 1 through Day 7 including rest and active recovery)
        ],
        "nutrition_plan": {{
            "overview": "Summary of nutritional strategy for this goal",
            "breakfast": "Detailed breakfast meal with estimated calories & protein",
            "lunch": "Detailed lunch meal with estimated calories & protein",
            "dinner": "Detailed dinner meal with estimated calories & protein",
            "snack": "Healthy snack idea with estimated calories & protein"
        }},
        "coaching_tips": [
            "Tip 1 for progressive overload and motivation",
            "Tip 2 for recovery and sleep",
            "Tip 3 for injury prevention and form",
            "Tip 4 for hydration and consistency"
        ]
    }}
    IMPORTANT: Respond ONLY with the JSON object. Do not include markdown code block markers or any conversational text.
    """

    try:
        interaction = gemini_client.interactions.create(
            model="gemini-3.8-flash",
            input=prompt
        )
        response_text = interaction.output_text.strip()
        
        # Clean potential markdown wrapping if present
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        elif response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        plan_json = json.loads(response_text)
        return plan_json
    except Exception as e:
        logger.error(f"Error calling Gemini API for plan generation: {e}. Falling back to smart rule engine.")
        fallback = generate_fallback_workout_and_diet(data)
        fallback["note"] = f"Generated by FitBuddy smart engine (Gemini API temporarily unavailable: {str(e)})"
        return fallback


def generate_ai_chat_response(user_message, history=None):
    """
    Responds to user questions in the interactive FitBuddy AI Coach chat widget.
    """
    if not gemini_client:
        # Friendly rule-based response
        low = user_message.lower()
        if "sore" in low or "pain" in low:
            return ("Muscle soreness (DOMS) is common, especially with new routines! 🧘 Stay hydrated, do light walking "
                    "or dynamic mobility, ensure you get 7-8 hours of sleep, and consume sufficient protein. "
                    "If you feel sharp or joint pain, rest immediately and consult a healthcare professional. "
                    "\n\n*(Tip: Add your GEMINI_API_KEY to .env for real-time contextual AI advice!)*")
        elif "snack" in low or "eat" in low or "food" in low:
            return ("Here are 3 great fitness snacks: \n1. 🥣 Greek yogurt with berries and honey (high protein & antioxidants)\n"
                    "2. 🍎 Apple slices with natural peanut butter (fiber + healthy fats)\n"
                    "3. 🥚 Hard-boiled eggs with a sprinkle of paprika and sea salt.\n\n"
                    "*(Tip: Set your GEMINI_API_KEY in .env for custom recipe ideas!)*")
        elif "squat" in low or "form" in low or "deadlift" in low:
            return ("Key form cues for lifting:\n- **Squats:** Keep chest tall, brace core like you're about to be punched, "
                    "drive knees out slightly in line with toes, hit parallel depth.\n- **Deadlifts:** Hinge at the hips, "
                    "keep bar touching shins, maintain neutral cervical spine.\n\n*(Connect Gemini API in .env for video form breakdown tips!)*")
        else:
            return ("Hello! I'm FitBuddy, your personal fitness & nutrition coach. "
                    "I can guide your workout routines, suggest meal plans, fix exercise form, and keep you motivated! "
                    "Feel free to ask any workout, diet, or recovery question. \n\n"
                    "*(Note: You are currently using the built-in smart assistant. Add a GEMINI_API_KEY to your .env file to enable live Gemini 3.8 Flash AI reasoning!)*")

    system_instruction = (
        "You are FitBuddy, an energetic, empathetic, and certified personal fitness coach & sports nutritionist. "
        "You offer evidence-based, safe, practical advice regarding workouts, strength training, weight loss, "
        "muscle hypertrophy, mobility, and healthy eating. "
        "Keep your tone motivating, clear, and structured with bullet points. "
        "Always remind the user to prioritize safety, proper warmup, and consult a physician for medical conditions."
    )

    full_prompt = f"System: {system_instruction}\nUser: {user_message}"
    
    try:
        interaction = gemini_client.interactions.create(
            model="gemini-3.8-flash",
            input=full_prompt
        )
        return interaction.output_text
    except Exception as e:
        logger.error(f"Error in Gemini chat: {e}")
        return f"FitBuddy Coach: I'm momentarily catching my breath! (API Error: {str(e)}). Try asking again in a few moments, or check your API key in .env."


# ==========================================
# FLASK WEB ROUTES
# ==========================================

@app.route("/")
def index():
    """Renders the main FitBuddy Single Page Application"""
    has_gemini = bool(gemini_client)
    return render_template("index.html", has_gemini=has_gemini)


@app.route("/api/status", methods=["GET"])
def api_status():
    """Returns application and AI engine status"""
    return jsonify({
        "status": "online",
        "app_name": "FitBuddy",
        "version": "2.0.0",
        "gemini_active": bool(gemini_client)
    })


@app.route("/api/calculate", methods=["POST"])
def api_calculate():
    """
    Receives user measurements and returns complete metabolic & macro breakdown.
    """
    try:
        data = request.get_json() or {}
        
        # Parse inputs with robust validation and defaults
        age = int(data.get("age", 25))
        gender = str(data.get("gender", "male")).strip()
        weight = float(data.get("weight", 70))  # in kg
        height = float(data.get("height", 175))  # in cm
        activity = str(data.get("activity", "moderate")).strip()
        goal = str(data.get("goal", "general_fitness")).strip()
        dietary_pref = str(data.get("dietary_pref", "omnivore")).strip()

        # Handle imperial units conversion if sent by user
        units = data.get("units", "metric")
        if units == "imperial":
            # weight was sent in lbs -> convert to kg
            weight = weight * 0.453592
            # height was sent in inches -> convert to cm
            height = height * 2.54

        if weight <= 20 or weight > 350 or height <= 50 or height > 280 or age < 10 or age > 110:
            return jsonify({"error": "Please provide realistic age, weight, and height values."}), 400

        results = compute_fitness_metrics(
            age=age,
            gender=gender,
            weight_kg=weight,
            height_cm=height,
            activity_level=activity,
            goal=goal,
            dietary_pref=dietary_pref
        )

        return jsonify({"success": True, "data": results})

    except Exception as e:
        logger.error(f"Error in /api/calculate: {e}")
        return jsonify({"error": f"Calculation error: {str(e)}"}), 400


@app.route("/api/generate-plan", methods=["POST"])
def api_generate_plan():
    """
    Generates a full 7-day workout and meal plan.
    Uses Gemini AI if configured, otherwise falls back to the smart rule engine.
    """
    try:
        data = request.get_json() or {}
        plan = generate_ai_fitness_plan_gemini(data)
        return jsonify({"success": True, "plan": plan})
    except Exception as e:
        logger.error(f"Error in /api/generate-plan: {e}")
        return jsonify({"error": f"Failed to generate plan: {str(e)}"}), 500


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Endpoint for conversational FitBuddy AI Personal Coach.
    """
    try:
        data = request.get_json() or {}
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"error": "Message cannot be empty."}), 400

        reply = generate_ai_chat_response(message)
        return jsonify({"success": True, "reply": reply})
    except Exception as e:
        logger.error(f"Error in /api/chat: {e}")
        return jsonify({"error": f"Chat service error: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    host = os.getenv("HOST", "127.0.0.1")
    debug_mode = os.getenv("FLASK_DEBUG", "1") == "1"
    
    print(f"\n=======================================================")
    print(f"[*] FitBuddy AI Web Server Running!")
    print(f"[*] Local URL: http://{host}:{port}")
    print(f"[*] Gemini Status: {'ACTIVE (Gemini 3.8 Flash)' if gemini_client else 'OFFLINE ENGINE (Ready - Add GEMINI_API_KEY to .env to upgrade)'}")
    print(f"=======================================================\n")
    
    app.run(host=host, port=port, debug=debug_mode)
