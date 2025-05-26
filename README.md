# VluationDashboard

# 📈 指数估值仪表盘 (Streamlit)

A lightweight Streamlit app that pulls index valuation data from 同花顺 _iFinD_  
and visualises it with scatter, distribution, and **bubble charts**.  
PE / PB 百分位自动分类为 **低估 🔻 · 适中 · 高估 🔺**, plus a sortable data table.

![screenshot](docs/screenshot.png)

---

## ✨ Features
| 功能 | 说明 |
|------|------|
| **Online API** | Always fetches live data from `djapi/index_eva/dj` (no CSV upload UI). |
| **Daily auto-refresh** | Container re-pulls data after 20:00 local time, or on manual refresh. |
| **Scatter & Bubble charts** | • Scatter: PE% vs PB% <br>• Bubble: adds bubble-size = dividend yield |
| **Distribution bar** | Quick view of how many indices fall in each valuation band. |
| **Ag-Grid table** | Sort / filter; columns in requested order (含 PE/PB 实际值、股息率). |
| **Footer cheatsheet** | Icons 🔻 🔺 ⚠️ + PE/PB 百分位规则 & 常用指标说明 |

---

## 🚀 Quick start (local)

```bash
git clone https://github.com/your-name/valuation-dashboard.git
cd valuation-dashboard
python -m venv .venv && source .venv/bin/activate  # or use conda
pip install -r requirements.txt
streamlit run app.py
