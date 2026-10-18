// DASHBOARD SETTINGS - the only file you edit for the dashboard.
// Use the SAME Firebase database URL as settings.py (no "/" at the end).
window.DASHBOARD_CONFIG = {
  firebaseUrl: "https://YOUR-PROJECT-default-rtdb.asia-southeast1.firebasedatabase.app",  // <-- CHANGE

  // Login: leave empty while the database is in "test mode".
  // After you lock the database (guide: "Before day 30"), fill in a dashboard user.
  apiKey: "",
  email: "",
  password: "",

  // Map centre (Kaduwela) and the depot (same as settings.py)
  depot: [6.9330, 79.9830],
  refreshSeconds: 15
};
