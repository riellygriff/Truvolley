from prefect import flow, task
from prefect_gcp.bigquery import BigQueryWarehouse
import polars as pl
import Glicko_Rating

@flow
def get_matches():
    query = '''
    select *
    FROM `rare-mender-353319.truvolley.volleyball_matches` 
    '''
    with BigQueryWarehouse.load("truvolley", validate=False) as warehouse:
        operation = query
        result = warehouse.fetch_all(operation)
    rows = [list(i) for i in result]
    columns = ['tournament_id','winner_1','winner_2','loser_1','loser_2']
    df = pl.DataFrame(rows, schema=columns)
    return df

@flow
def get_players():
    query = '''
    select p.player_name,p.tournament,p.rating,p.rd,p.vol
    from `truvolley.players` p
    join(
      select player_name, max(tournament) as tournament
      from `truvolley.players`
      group by player_name
    ) r on p.player_name=r.player_name and p.tournament = r.tournament
    '''
    with BigQueryWarehouse.load("truvolley", validate=False) as warehouse:
        operation = query
        result = warehouse.fetch_all(operation)
    rows = [list(i) for i in result]
    columns = ['players','tournament_id','rating','rd','vol']
    df = pl.DataFrame(rows, schema=columns)
    return df

@task
def add_teams(matches):
    df = matches.with_columns((pl.col('winner_1')+'_'+pl.col('winner_2')).alias('winners'))
    df = df.with_columns((pl.col('loser_1')+'_'+pl.col('loser_2')).alias('losers'))
    return df

@task
def add_ratings(matches,players):
    df = matches.join(players, left_on='winner_1',right_on='players',suffix='w1',how='left')
    df = df.join(players, left_on='winner_2',right_on='players',suffix='w2',how='left')
    df = df.join(players, left_on='loser_1',right_on='players',suffix='l1',how='left')
    df = df.join(players, left_on='loser_2',right_on='players',suffix='l2',how='left')
    df = df.with_columns(pl.col('rating').fill_null(1500),
                         pl.col('ratingw2').fill_null(1500),
                         pl.col('ratingl1').fill_null(1500),
                         pl.col('ratingl2').fill_null(1500),
                         pl.col('rd').fill_null(350),
                         pl.col('rdw2').fill_null(350),
                         pl.col('rdl1').fill_null(350),
                         pl.col('rdl2').fill_null(350),
                         pl.col('vol').fill_null(.06),
                         pl.col('volw2').fill_null(.06),
                         pl.col('voll1').fill_null(.06),
                         pl.col('voll2').fill_null(.06)
                         )
    return df

@task
def list_teams(matches):
    teams = matches.select(pl.col('winners').alias('teams'))
    teams = teams.vstack(matches.select(pl.col('losers').alias('teams')))
    teams = teams.unique()
    all_teams = [teams[i,0] for i in range(len(teams))]
    all_teams = sorted(all_teams)
    # print(all_teams)
    return all_teams

@task
def get_results(df,teams):
    input_all = []
    ctx = pl.SQLContext(matches=df)
    for team in teams:
        input_fields = [team]
        outcomes=[]
        ratings=[]
        rd = []
        p1_rate=[]
        p1_rd=[]
        p1_vol=[]
        p2_rate=[]
        p2_rd=[]
        p2_vol=[]
        results = ctx.execute(f'''
                                select *
                                from matches
                                where winners ='{team}' or losers = '{team}'
                                ''').collect()

        # print(results)
        for i in range(len(results)):
            row = results.row(i)
            # print(row)
            if row[5]==team:
                outcomes.append(1)
                opp_rate=(row[13]+row[16])/2
                ratings.append(opp_rate)
                opp_rd = (row[14] + row[17]) / 2
                rd.append(opp_rd)
                p1_rate.append(row[7])
                p1_rd.append(row[8])
                p1_vol.append(row[9])
                p2_rate.append(row[10])
                p2_rd.append(row[11])
                p2_vol.append(row[12])

            if row[6]==team:
                outcomes.append(0)
                opp_rate=(row[7]+row[10])/2
                ratings.append(opp_rate)
                opp_rd = (row[8] + row[11]) / 2
                rd.append(opp_rd)
                p1_rate.append(row[13])
                p1_rd.append(row[14])
                p1_vol.append(row[15])
                p2_rate.append(row[16])
                p2_rd.append(row[17])
                p2_vol.append(row[18])

        input_fields.append(sum(p1_rate)/len(p1_rate))
        input_fields.append(sum(p2_rate)/len(p2_rate))
        input_fields.append(sum(p1_rd)/len(p1_rd))
        input_fields.append(sum(p2_rd)/len(p2_rd))
        input_fields.append((sum(p1_vol)+sum(p2_vol))/(len(p1_vol)+len(p2_vol)))
        input_fields.append(ratings)
        input_fields.append(rd)
        input_fields.append(outcomes)
        input_all.append(input_fields)

    return input_all

@task
def new_ratings(results):
    updated_stats=[]
    for result in results:
        updates = Glicko_Rating.Player(rating=(result[1] + result[2])/2,rd=(result[3] + result[4])/2,vol=result[5])
        updates.update_player(result[6], result[7], result[8])
        p1_rate = (result[1] / (result[1] + result[2])) * updates.rating * 2
        p2_rate = (result[2] / (result[1] + result[2])) * updates.rating * 2
        p1_rd = (result[3] / (result[3] + result[4])) * updates.rd * 2
        p2_rd = (result[4] / (result[3] + result[4])) * updates.rd * 2

        player = result[0].split('_')
        player_1 = [player[0],p1_rate,p1_rd,updates.vol]
        player_2 = [player[1], p2_rate, p2_rd, updates.vol]
        # print(player_1)
        # print(player_2)
        updated_stats.append(player_1)
        updated_stats.append(player_2)
    return updated_stats

@flow
def tru_rating():
    matches = get_matches()
    players = get_players()
    last_tour = players.select(pl.col('tournament_id').max()).row(0)[0]
    players = players.drop('tournament_id')
    matches = matches.filter(pl.col('tournament_id')>last_tour)
    tournaments = matches.select(pl.col('tournament_id')).unique().sort('tournament_id')
    for i in range(len(tournaments)):
        tournament = tournaments.row(i)[0]
        print(tournament)

        df = matches.filter(pl.col('tournament_id') == tournament)
        df = add_teams(df)
        df = add_ratings(df,players)
        teams= list_teams(df)
        results = get_results(df,teams)
        ratings = new_ratings(results)
        ratings = pl.DataFrame(ratings,schema=['players','rating','rd','vol']).unique()
        ratings = ratings.groupby('players').max()
        for i in range(len(ratings)):
            row = ratings.row(i)
            print(row)
            query = f'''
                   insert `truvolley.volleyball_matches` (player_name,tournament,rating,rd,vol)
                   values("{row[0]}",{tournament},{row[1]},{row[2]},{row[3]})
                   '''
            print(query)

            with BigQueryWarehouse.load("truvolley", validate=False) as warehouse:
                operation = query
                warehouse.execute(operation)
        players = players.update(ratings,on='players',how='outer')

tru_rating()
