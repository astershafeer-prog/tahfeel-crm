
def calculate_target_achievement(staff_id, revenue):
  target = MonthlyTarget.query.filter_by(user_id=staff_id).first()
  if target:
    achievement = (revenue / target.amount_target) * 100
    return round(achievement, 2)
  return 0
