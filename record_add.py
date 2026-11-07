# record_add.py
from flask import Blueprint, request, render_template, redirect, url_for, flash
import datetime
import math # 修复 BUG-2: 引入 math 模块
import json

# 创建蓝图，提供给成员A在 app.py 中注册集成
record_add_bp = Blueprint('record_add', __name__)

@record_add_bp.route('/add', methods=['GET', 'POST'])
def add():
    if request.method == 'POST':
        # 1. 接收前端表单数据
        record_type = request.form.get('type')
        date_str = request.form.get('date')
        amount_str = request.form.get('amount')
        category = request.form.get('category')
        account = request.form.get('account')
        note = request.form.get('note', '').strip()

        # ==========================================
        # 2. 严格的后端校验
        # ==========================================
        # (1) 必填项空值校验
        if not all([record_type, date_str, amount_str, category, account]):
            flash('提交失败：收支类型、日期、金额、类别、账户均为必填项！', 'error')
            return redirect(url_for('record_add.add'))
            
        # (2) 收支类型校验
        if record_type not in ['income', 'expense']:
            flash('提交失败：非法的收支类型！', 'error')
            return redirect(url_for('record_add.add'))

        # (3) 日期格式校验 (修复观察项1：对齐成员B的严格校验)
        try:
            # fromisoformat 严格要求 YYYY-MM-DD 格式，不允许单数日不补零
            datetime.date.fromisoformat(date_str)
        except ValueError:
            flash('提交失败：日期格式错误，必须为严格的 YYYY-MM-DD 格式！', 'error')
            return redirect(url_for('record_add.add'))

        # (4) 金额格式与大小校验 (修复 BUG-2: 防御 NaN 注入)
        try:
            amount = float(amount_str)
            # 使用 math.isfinite 拦截 NaN 和 Inf
            if not math.isfinite(amount) or amount <= 0:
                flash('提交失败：金额无效，必须是大于 0 的有效数字！', 'error')
                return redirect(url_for('record_add.add'))
        except ValueError:
            flash('提交失败：金额必须是有效的数字！', 'error')
            return redirect(url_for('record_add.add'))

        # (5) 类别合法性校验 (修复 BUG-3: 确保类别存在)
        try:
            from category import list_categories
            valid_categories = [cat['name'] for cat in list_categories()]
            if category not in valid_categories:
                flash(f'提交失败：选择的类别"{category}"不存在或不合法！', 'error')
                return redirect(url_for('record_add.add'))
        except ImportError:
            # 独立测试兜底：如果没有 category 模块，则跳过严格校验
            pass

        # ==========================================
        # 3. 构造数据并调用成员B的存储接口
        # ==========================================
        new_record = {
            "type": record_type,
            "date": date_str,
            "amount": round(amount, 2),
            "category": category,
            "account": account,          
            "note": note
        }

        try:
            from storage import add_record
            add_record(new_record)
            flash('记账成功！', 'success')
            return redirect(url_for('record_add.add'))
            
        except ImportError:
            flash(f'[独立测试] 记账成功！{date_str} / {category} / {amount}元 (账户: {account})', 'success')
            return redirect(url_for('record_add.add'))
        except Exception as e:
            flash(f'系统错误：数据保存失败 ({str(e)})', 'error')
            return redirect(url_for('record_add.add'))

    # ==========================================
    # GET 请求：渲染录入页面并对接成员F的分类
    # ==========================================
    try:
        from category import list_categories
        categories = list_categories()
    except ImportError:
        categories = [
            {"name": "饮食", "type": "expense", "icon": "🍜"},
            {"name": "交通", "type": "expense", "icon": "🚌"},
            {"name": "购物", "type": "expense", "icon": "🛍️"},
            {"name": "工资", "type": "income", "icon": "💰"},
            {"name": "兼职", "type": "income", "icon": "💴"}
        ]

    return render_template('record_add.html', categories_json=json.dumps(categories))