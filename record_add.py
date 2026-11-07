# record_add.py
from flask import Blueprint, request, render_template, redirect, url_for, flash
import datetime
import json

# 创建蓝图，提供给成员A在 app.py 中注册集成
record_add_bp = Blueprint('record_add', __name__)

@record_add_bp.route('/add', methods=['GET', 'POST'])
def add():
    if request.method == 'POST':
        # 1. 接收前端表单数据 (包含对接成员B的 account 字段)
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

        # (3) 日期格式校验
        try:
            datetime.datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            flash('提交失败：日期格式错误，应为 YYYY-MM-DD！', 'error')
            return redirect(url_for('record_add.add'))

        # (4) 金额格式与大小校验
        try:
            amount = float(amount_str)
            if amount <= 0:
                flash('提交失败：金额必须大于 0！', 'error')
                return redirect(url_for('record_add.add'))
        except ValueError:
            flash('提交失败：金额必须是有效的数字！', 'error')
            return redirect(url_for('record_add.add'))

        # ==========================================
        # 3. 构造数据并调用成员B的存储接口
        # ==========================================
        new_record = {
            "type": record_type,
            "date": date_str,
            "amount": round(amount, 2),  # 强制保留两位小数
            "category": category,
            "account": account,          
            "note": note
        }

        try:
            # 联调时调用成员B的接口
            from storage import add_record
            add_record(new_record)
            flash('记账成功！', 'success')
            
            # TODO: 成员D列表页写好后，改为跳转到列表页
            # return redirect(url_for('record_list.list_records'))
            return redirect(url_for('record_add.add'))
            
        except ImportError:
            # 兼容：如果成员B的代码还没就绪，先模拟成功防止崩溃
            flash(f'[独立测试] 记账成功！{date_str} / {category} / {amount}元 (账户: {account})', 'success')
            return redirect(url_for('record_add.add'))
        except Exception as e:
            flash(f'系统错误：数据保存失败 ({str(e)})', 'error')
            return redirect(url_for('record_add.add'))

    # ==========================================
    # GET 请求：渲染录入页面并对接成员F的分类
    # ==========================================
    try:
        # 联调时调用成员F的真实接口
        from category import list_categories
        categories = list_categories()
    except ImportError:
        # 兼容：如果成员F的代码还没就绪，使用带 icon 的模拟数据
        categories = [
            {"name": "饮食", "type": "expense", "icon": "🍜"},
            {"name": "交通", "type": "expense", "icon": "🚌"},
            {"name": "购物", "type": "expense", "icon": "🛍️"},
            {"name": "工资", "type": "income", "icon": "💰"},
            {"name": "兼职", "type": "income", "icon": "💴"}
        ]

    return render_template('record_add.html', categories_json=json.dumps(categories))