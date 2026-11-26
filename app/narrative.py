"""Deterministic Persian prose built solely from returned database rows.

No model-written factual text and no reference/evaluation dataset dependency.
"""
from __future__ import annotations

_DIGITS=str.maketrans('0123456789','۰۱۲۳۴۵۶۷۸۹')
_TERMS={
    'goals':'گل','goal_count':'گل','goals_scored':'گل','late_goals':'گل',
    'points':'امتیاز','clean_sheets':'کلین‌شیت','yellow_cards':'کارت زرد',
    'red_cards':'کارت قرمز','red_card_count':'کارت قرمز',
    'matches_played':'مسابقه','penalties_awarded':'پنالتی','penalties_converted':'پنالتی گل‌شده',
    'minutes':'دقیقه','minutes_played':'دقیقه','total_minutes':'دقیقه',
}

def _fa(value):
    if value is None:return 'نامشخص'
    if isinstance(value,bool):return 'بله' if value else 'خیر'
    return str(value).translate(_DIGITS)

def summarize(data: dict) -> str:
    rows=data.get('rows') or []
    columns=list(data.get('columns') or [])
    count=int(data.get('row_count',len(rows)))
    if not rows:
        return 'برای این پرسش در داده‌های ثبت‌شده ردیفی پیدا نشد؛ نتیجه‌ای حدس زده نشده است.'
    # Prefer the two top displayed, readable entities in any query with a numeric metric.
    if len(rows)>1 and columns and len(rows[0])==len(columns):
        metrics=[i for i in range(len(columns)) if all(isinstance(r[i],(int,float)) and not isinstance(r[i],bool) for r in rows[:2]) and not columns[i].lower().endswith('_id') and columns[i].lower() not in ('round','minute','added_time')]
        label_idx=next((i for i in range(len(columns)) if all(isinstance(r[i],str) for r in rows[:2]) and 'date' not in columns[i].lower()),None)
        if label_idx is not None and metrics:
            metric_idx=metrics[-1]
            # Prefer a clearly named result measure over a numeric entity ID/round.
            metric_idx=metrics[-1]
            unit=_TERMS.get(columns[metric_idx].lower(),columns[metric_idx].replace('_',' '))
            snippets=[]
            for row in rows[:2]:
                club_idx=next((i for i,col in enumerate(columns)
                               if i!=label_idx and ('team' in col.lower() or 'club' in col.lower())
                               and isinstance(row[i],str)),None)
                name=_fa(row[label_idx])+(f' ({_fa(row[club_idx])})' if club_idx is not None else '')
                snippets.append(f'{name} با {_fa(row[metric_idx])} {unit}')
            text=' و '.join(snippets)
            return f'بر اساس ردیف‌های دیتابیس، {text} در نتایج دیده می‌شوند. جدول کامل شامل {_fa(count)} ردیف است.'
    # A single aggregate or multi-field match: expose observed labels + values.
    first=rows[0]
    if len(first)==len(columns):
        details=', '.join(f'{_TERMS.get(col.casefold(), col.replace("_"," "))}: {_fa(val)}'
                          for col,val in list(zip(columns,first))[:6])
        suffix=(f'؛ در مجموع {_fa(count)} ردیف ثبت شده است.' if count>1 else '.')
        return f'طبق داده‌های ثبت‌شده، {details}{suffix}'
    return f'پاسخ از {_fa(count)} ردیف واقعی دیتابیس به دست آمده است.'
