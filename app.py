from flask import Flask, render_template, request, redirect, url_for
import pandas as pd
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# File paths
MACHINES_CSV = "machines.csv"
ORDERS_CSV = "orders.csv"
INVENTORY_CSV = "inventory.csv"

def load_csv(file_path):
    """Load CSV file."""
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        return df
    return pd.DataFrame()

def parse_datetime(datetime_string):
    """Parse datetime string into a datetime object."""
    formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M"]
    for fmt in formats:
        try:
            return datetime.strptime(datetime_string, fmt)
        except ValueError:
            continue
    raise ValueError(f"Time data '{datetime_string}' does not match any known format.")

@app.route("/", methods=["GET", "POST"])
def index():
    machines_data = load_csv(MACHINES_CSV).to_dict(orient="records")
    if request.method == "POST":
        plans = []
        for machine in machines_data:
            name = machine["name"]
            plans.append({
                "name": name,
                "start_datetime": request.form[f"{name}_start_datetime"],
                "shifts_per_day": int(request.form[f"{name}_shifts_per_day"]),
                "hours_per_shift": int(request.form[f"{name}_hours_per_shift"]),
                "employees_available": int(request.form[f"{name}_employees_available"]),
            })

        # Handle file uploads
        if "inventory_file" in request.files:
            inventory_file = request.files["inventory_file"]
            if inventory_file:
                inventory_file.save(INVENTORY_CSV)

        if "orders_file" in request.files:
            orders_file = request.files["orders_file"]
            if orders_file:
                orders_file.save(ORDERS_CSV)

        return simulate(plans)

    return render_template("index.html", machines_data=machines_data)

@app.route("/simulate", methods=["POST", "GET"])
def simulate(plans=None):
    if plans is None:
        return redirect(url_for("index"))

    machines_data = load_csv(MACHINES_CSV)
    orders_data = load_csv(ORDERS_CSV)
    inventory_data = load_csv(INVENTORY_CSV)

    total_consumption = {}
    stockouts = {}
    inventory_status = {}
    machine_results = []
    orders_results = []
    total_time = 0  # Cumulative processing time

    for index, row in inventory_data.iterrows():
        total_consumption[row["material_name"]] = 0
        stockouts[row["material_name"]] = 0

    for plan in plans:
        machine_params = machines_data[machines_data["name"] == plan["name"]].iloc[0]
        hours_available = plan["shifts_per_day"] * plan["hours_per_shift"]
        production_rate = machine_params["rate_kg_h"]
        scrap_rate = machine_params["scrap"]
        downtime_rate = machine_params["downtime"]
        material_needed = machine_params["material_kg_unit"]
        employees_needed = machine_params["employees_needed"]

        if plan["employees_available"] < employees_needed:
            machine_results.append({
                "machine": plan["name"],
                "status": "Not enough employees",
                "production": 0,
                "material_consumed": 0,
                "used_capacity": 0,
                "downtime_rate": downtime_rate,
                "scrap_rate": scrap_rate,
            })
            continue

        potential_production = hours_available * production_rate
        actual_production = potential_production * (1 - scrap_rate)
        material_used = actual_production * material_needed

        total_consumption[machine_params["material_name"]] += material_used

        machine_results.append({
            "machine": plan["name"],
            "status": "Simulated",
            "production": round(actual_production,0),
            "material_consumed": material_used,
            "used_capacity": round((actual_production / potential_production),2),
            "downtime_rate": downtime_rate,
            "scrap_rate": scrap_rate,
        })

    for material, consumed in total_consumption.items():
        row = inventory_data[inventory_data["material_name"] == material].iloc[0]
        initial_level = row["initial_level_kg"]
        reorder_quantity = row["reorder_quantity_kg"]
        reorder_triggered = "Yes" if consumed > initial_level else "No"  # Determine if reorder occurred
        shortage_quantity = consumed - initial_level if consumed > initial_level else 0
        if consumed > initial_level:
            stockouts[material] += 1
            final_level = reorder_quantity + initial_level
            shortage_quantity = consumed - initial_level 
        else:
            final_level = initial_level - consumed
            shortage_quantity = 0
        inventory_status[material] = {
            "initial": initial_level,
            "consumed": round(consumed,0),
            "reorder_quantity": reorder_quantity if final_level > initial_level else 0,
            "final": final_level,
            "stockouts": stockouts[material],
            "reorder_triggered": reorder_triggered,
            "shortage_quantity": round(shortage_quantity,0)
        }

    
    # Calculate order due dates
    orders_data["due_date"] = orders_data.apply(
        lambda row: parse_datetime(row["entry_date"]) + timedelta(hours=row["agreed_lead_time"]), axis=1
    )
    orders_data["processing_time"] = orders_data["order_size"] / machines_data.set_index("name").loc[
        orders_data["machine_name"], "rate_kg_h"
    ].values

    # Sort orders by priority
    sorted_orders = orders_data.sort_values(by=["due_date", "processing_time"]).to_dict(orient="records")

    for order in sorted_orders:
        entry_date = parse_datetime(order["entry_date"])
        due_date = entry_date + timedelta(hours=order["agreed_lead_time"])
        processing_time = order["order_size"] / machines_data.set_index("name").loc[order["machine_name"], "rate_kg_h"]
        wait_time = total_time
        lead_time = wait_time + processing_time

        # Check inventory for material availability
        material_needed = machines_data.set_index("name").loc[order["machine_name"], "material_kg_unit"] * order["order_size"]
        material_available = inventory_data.set_index("material_name").loc[order["material_name"], "material_quantity"]

        if material_available >= material_needed:
            completed_quantity = order["order_size"]
            inventory_data.loc[inventory_data["material_name"] == order["material_name"], "material_quantity"] -= material_needed
            status = "Completed"
            shortage_quantity = 0
        else:
            completed_quantity = material_available / machines_data.set_index("name").loc[order["machine_name"], "material_kg_unit"]
            inventory_data.loc[inventory_data["material_name"] == order["material_name"], "material_quantity"] = 0
            status = "Partial" if completed_quantity > 0 else "Not Completed"
            shortage_quantity = order["order_size"] - completed_quantity

        total_time += processing_time
        on_time = "Yes" if lead_time <= order["agreed_lead_time"] else "No"

        orders_results.append({
            "order_id": order["order_id"],
            "status": status,
            "completed_quantity": round(completed_quantity,0),
            "shortage_quantity": shortage_quantity,
            "due_date": due_date.strftime("%Y-%m-%d %H:%M"),
            "entry_date": entry_date.strftime("%Y-%m-%d %H:%M"),
            "on_time": on_time,
            "lead_time": round(lead_time,1)
        })

    return render_template(
        "results.html",
        machines=machine_results,
        inventory=inventory_status,
        orders=orders_results,
    )

if __name__ == "__main__":
    app.run(debug=True)
