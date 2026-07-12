from __future__ import annotations
import json
from random import randint
from app.services import get_effective_stats

STYLES = {
    "berserk": {"name":"Берсерк","damage":1.25,"defense":0.85,"magic":1.0,"dodge":0},
    "guardian": {"name":"Страж","damage":0.90,"defense":1.30,"magic":1.0,"dodge":0},
    "magister": {"name":"Магистр","damage":0.90,"defense":1.0,"magic":1.25,"dodge":0},
    "duelist": {"name":"Дуэлянт","damage":1.0,"defense":0.95,"magic":1.0,"dodge":12},
}
ACTIONS={"attack","magic","defend","dodge","critical","potion"}

def log_list(duel):
    try: return json.loads(duel.battle_log or "[]")
    except Exception: return []

def append_log(duel,text):
    logs=log_list(duel); logs.append(text); duel.battle_log=json.dumps(logs[-30:],ensure_ascii=False)

def side(duel, character_id):
    return "challenger" if duel.challenger_id==character_id else "opponent"

def other_side(name): return "opponent" if name=="challenger" else "challenger"

def getv(duel,side_name,field): return getattr(duel,f"{side_name}_{field}")
def setv(duel,side_name,field,value): setattr(duel,f"{side_name}_{field}",value)

def style_data(duel,side_name): return STYLES.get(getv(duel,side_name,"style"),STYLES["guardian"])

def fifty_fifty(stat_value:int)->int:
    # Ровно половина результата — расчёт персонажа, половина — случайность.
    random_part=randint(0,max(1,stat_value*2))
    return max(1,(stat_value+random_part)//2)

async def initialize_duel(session,duel,challenger,opponent):
    cs=await get_effective_stats(session,challenger); os=await get_effective_stats(session,opponent)
    duel.challenger_hp=cs["health"]+cs["endurance"]*3+challenger.level*8
    duel.opponent_hp=os["health"]+os["endurance"]*3+opponent.level*8
    duel.challenger_mana=cs["mana"]+cs["intelligence"]*2+challenger.level*2
    duel.opponent_mana=os["mana"]+os["intelligence"]*2+opponent.level*2
    duel.challenger_stamina=100+cs["endurance"]*2
    duel.opponent_stamina=100+os["endurance"]*2
    first_score=(cs["agility"]+challenger.level)+randint(0,cs["luck"]+40)
    second_score=(os["agility"]+opponent.level)+randint(0,os["luck"]+40)
    duel.turn_character_id=challenger.id if first_score>=second_score else opponent.id
    duel.status="active"
    append_log(duel,f"⚔ Дуэль началась. Первый ход: {'challenger' if duel.turn_character_id==challenger.id else 'opponent'}.")

async def perform_action(session,duel,actor,target,action):
    if action not in ACTIONS: raise ValueError("Неизвестное действие")
    a=side(duel,actor.id); t=other_side(a)
    ast=await get_effective_stats(session,actor); tst=await get_effective_stats(session,target)
    astyle=style_data(duel,a); tstyle=style_data(duel,t)
    stamina=getv(duel,a,"stamina")
    if action in {"attack","magic","critical","dodge"} and stamina<10:
        raise ValueError("Недостаточно выносливости")

    if action=="defend":
        setv(duel,a,"defending",True); setv(duel,a,"stamina",min(160,stamina+18))
        text=f"🛡 {actor.name} встаёт в защитную стойку."
    elif action=="dodge":
        setv(duel,a,"dodging",True); setv(duel,a,"stamina",stamina-10)
        text=f"🏃 {actor.name} готовится уклониться."
    elif action=="potion":
        if getv(duel,a,"potion_used"): raise ValueError("Зелье уже использовано")
        heal=25+actor.level*3+fifty_fifty(ast["luck"]+ast["intelligence"])
        setv(duel,a,"hp",getv(duel,a,"hp")+heal); setv(duel,a,"potion_used",True)
        text=f"🧪 {actor.name} восстанавливает {heal} HP."
    else:
        if action=="magic":
            mana_cost=max(12,28-ast["intelligence"]//3)
            if getv(duel,a,"mana")<mana_cost: raise ValueError("Недостаточно маны")
            setv(duel,a,"mana",getv(duel,a,"mana")-mana_cost)
            setv(duel,a,"stamina",stamina-12)
            stat_base=ast["magic"]*3+ast["intelligence"]+actor.level*3
            raw=fifty_fifty(stat_base); damage=int(raw*astyle["magic"])
            label="✨ заклинанием"
        elif action=="critical":
            setv(duel,a,"stamina",stamina-22)
            chance=min(70,20+ast["luck"]//2+ast["agility"]//4)
            stat_base=ast["strength"]*2+ast["agility"]+actor.level*3
            raw=fifty_fifty(stat_base)
            if randint(1,100)<=chance:
                damage=int(raw*1.9*astyle["damage"]); label="💥 критическим ударом"
            else:
                damage=max(1,int(raw*.45)); label="💨 неудачным критическим ударом"
        else:
            setv(duel,a,"stamina",stamina-10)
            stat_base=ast["strength"]*3+ast["agility"]//2+actor.level*3
            damage=int(fifty_fifty(stat_base)*astyle["damage"]); label="⚔ атакой"

        dodge_chance=min(65,8+tst["agility"]//2+tst["luck"]//4+tstyle["dodge"])
        if getv(duel,t,"dodging"):
            dodge_chance=min(85,dodge_chance+25); setv(duel,t,"dodging",False)
        if randint(1,100)<=dodge_chance:
            damage=0; text=f"💨 {target.name} уклоняется от действия {actor.name}."
        else:
            defense_factor=max(.35,1-(tst["endurance"]+target.level*2)/250)
            defense_factor/=tstyle["defense"]
            if getv(duel,t,"defending"):
                defense_factor*=.48; setv(duel,t,"defending",False)
            damage=max(1,int(damage*defense_factor))
            setv(duel,t,"hp",max(0,getv(duel,t,"hp")-damage))
            text=f"{label} {actor.name} наносит {damage} урона."

    append_log(duel,text)
    if getv(duel,t,"hp")<=0:
        duel.status="finished"; duel.winner_id=actor.id
        return True,text
    duel.turn_character_id=target.id; duel.round_number+=1
    return False,text
