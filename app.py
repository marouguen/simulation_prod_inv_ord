from flask import Flask, render_template, request
import pandas as pd
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# CSV file paths
MACHINES_CSV = "machines.csv"
ORDERS_CSV = "orders.csv"
INVENTORY_CSV = "inventory.csv"

def load_csv(file_path):
    """Load a CSV file into a Pandas DataFrame."""
    print(f"Loading: {file_path}")
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        print(f"Loaded {file_path} with columns: {list(df.columns)}")
        return df
    return pd.DataFrame()

def parse_datetime(datetime_string):
    """Parse datetime strings in multiple formats."""
    formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M"]
    for fmt in formats:
        try:
            return datetime.strptime(datetime_string, fmt)
        except ValueError:
            continue
    raise ValueError(f"Time data '{datetime_string}' does not match any known format.")

@app.route("/", methods=["GET", "POST"])
def index():
    machines_data = load_csv(MACHINES_CSV).to_dict("records")

    if request.method == "POST":
        plans = []
        for machine in machines_data:
            name = machine["name"]
            plans.append({
                "name": name,
                "shifts_per_day": int(request.form.get(f"{name}_shifts_per_day", 0)),
                "hours_per_shift": int(request.form.get(f"{name}_hours_per_shift", 0)),
                "employees_available": int(request.form.get(f"{name}_employees_available", 0)),
            })

        # Save uploaded files
        if "inventory_file" in request.files:
            inventory_file = request.files["inventory_file"]
            if inventory_file:
                inventory_file.save(INVENTORY_CSV)

        if "orders_file" in request.files:
            orders_file = request.files["orders_file"]
            if orders_file:
                orders_file.save(ORDERS_CSV)

        # Pass plans to simulate route
        return simulate(plans)

    return render_template("index.html", machines_data=machines_data)

@app.route("/simulate", methods=["POST"])
def simulate(plans):
    machines_data = load_csv(MACHINES_CSV)
    orders_data = load_csv(ORDERS_CSV)
    inventory_data = load_csv(INVENTORY_CSV)

    print("Plans:", plans)
    print("Orders Data:", orders_data)
    print("Inventory Data:", inventory_data)

    machine_results = []
    total_consumption = {material: 0 for material in inventory_data["material_name"]}
    stockouts = 0

    # Process machine plans
    for plan in plans:
        try:
            machine_params = machines_data[machines_data["name"] == plan["name"]].iloc[0]
        except IndexError:
            print(f"Machine '{plan['name']}' not found!")
            continue

        hours_available = plan["shifts_per_day"] * plan["hours_per_shift"]
        production_rate = machine_params["rate_kg_h"]
        scrap_rate = machine_params["scrap"] / 100
        downtime_rate = machine_params["downtime"] / 100
        material_needed = machine_params["material_kg_unit"]

        production = production_rate * hours_available * (1 - scrap_rate)
        material_used = production * material_needed
        downtime_hours = hours_available * downtime_rate
        used_capacity = (production / (hours_available * production_rate)) * 100

        total_consumption[machine_params["material_name"]] += material_used

        machine_results.append({
            "machine": plan["name"],
            "production": production,
            "material_consumed": material_used,
            "employees_needed": machine_params["employees_needed_shift"],
            "average_lead_time": hours_available / production_rate,
            "used_capacity": used_capacity,
            "downtime_rate": downtime_rate * 100,
            "scrap_rate": scrap_rate * 100,
        })

    print("Machine Results:", machine_results)

    # Process inventory
    inventory_metrics = []
    for _, material in inventory_data.iterrows():
        initial_level = material["initial_level_kg"]
        final_level = initial_level - total_consumption[material["material_name"]]
        if final_level < 0:
            stockouts += 1
        inventory_metrics.append({
            "material": material["material_name"],
            "initial_level": initial_level,
            "final_level": final_level,
        })

    print("Inventory Metrics:", inventory_metrics)
    print("Stockouts:", stockouts)

    # Process orders
    orders_results = []
    for _, order in orders_data.iterrows():
        entry_date = parse_datetime(order["entry_date"])
        due_date = entry_date + timedelta(hours=order["agreed_lead_time"])
        lead_time = (due_date - entry_date).total_seconds() / 3600
        completed_quantity = min(order["order_size"], sum([m["production"] for m in machine_results]))
        status = "Completed" if completed_quantity >= order["order_size"] else "Pending"

        orders_results.append({
            "order_id": order["order_id"],
            "status": status,
            "completed_quantity": completed_quantity,
            "lead_time": lead_time,
            "on_time": "Yes" if status == "Completed" else "No",
        })

    print("Orders Results:", orders_results)

    return render_template(
        "results.html",
        machines=machine_results,
        inventory=inventory_metrics,
        stockouts=stockouts,
        orders=orders_results
    )

if __name__ == "__main__":
    app.run(debug=True)
