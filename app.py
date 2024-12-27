from flask import Flask, render_template, request, redirect
import pandas as pd
import os

app = Flask(__name__)

# CSV file paths
MACHINES_CSV = "machines.csv"
ORDERS_CSV = "orders.csv"
INVENTORY_CSV = "inventory.csv"

# Utility to load CSV files
def load_csv(file_path):
    if os.path.exists(file_path):
        return pd.read_csv(file_path)
    return pd.DataFrame()

@app.route("/", methods=["GET", "POST"])
def index():
    machines_data = load_csv(MACHINES_CSV).to_dict(orient="records")
    
    if request.method == "POST":
        plans = []
        
        # Collect machine-specific inputs
        for machine in machines_data:
            machine_name = machine["name"]
            plans.append({
                "name": machine_name,
                "start_datetime": request.form[f"{machine_name}_start_datetime"],
                "employees_available": int(request.form[f"{machine_name}_employees_available"]),
                "shifts_per_day": int(request.form[f"{machine_name}_shifts_per_day"]),
                "hours_per_shift": int(request.form[f"{machine_name}_hours_per_shift"]),
            })

        # Handle file uploads
        if "inventory_file" in request.files:
            inventory_file = request.files["inventory_file"]
            if inventory_file.filename:
                inventory_file.save(INVENTORY_CSV)

        if "orders_file" in request.files:
            orders_file = request.files["orders_file"]
            if orders_file.filename:
                orders_file.save(ORDERS_CSV)

        # Redirect to simulate with plans
        return render_template("results.html", plans=plans)
    
    return render_template("index.html", machines_data=machines_data)

@app.route("/simulate", methods=["POST"])
def simulate():
    machines_data = load_csv(MACHINES_CSV)
    inventory_data = load_csv(INVENTORY_CSV)
    orders_data = load_csv(ORDERS_CSV)

    # Process simulation logic (example results below)
    machine_results = [
        {"machine": "Prensa 1", "production": 5000, "material_consumed": 300, "employees_needed": 7},
        {"machine": "Vertical", "production": 4500, "material_consumed": 250, "employees_needed": 10},
    ]
    inventory_results = [
        {"material": "Aluminium", "initial_level": 1000, "final_level": 700},
        {"material": "Powder Coating", "initial_level": 500, "final_level": 250},
    ]
    orders_results = [
        {"order_id": 1, "status": "Completed", "completed_quantity": 300, "on_time": "Yes"},
        {"order_id": 2, "status": "Pending", "completed_quantity": 0, "on_time": "No"},
    ]

    return render_template(
        "results.html",
        machines=machine_results,
        inventory=inventory_results,
        orders=orders_results,
    )

if __name__ == "__main__":
    app.run(debug=True)
