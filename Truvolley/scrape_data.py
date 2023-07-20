import requests
import datetime
from bs4 import BeautifulSoup
from prefect import flow, task
from prefect_gcp.bigquery import BigQueryWarehouse


@task
def get_avp_tournaments(year):
    tournaments =[]
    past = past_tournaments()
    url = f'http://bvbinfo.com/Season.asp?AssocID=1&Year={year}'
    page = requests.get(url)
    soup = BeautifulSoup(page.content, "html.parser")
    results = soup.find_all('a')
    for result in results:
        link = result.get('href')
        if 'Tournament' in link:
            link = link[link.find('=')+1:]
            # print(link)
            if int(link) not in past:
                tournaments.append(link)
    return tournaments


def past_tournaments():
    query = '''
    select distinct tournament_id 
    FROM `rare-mender-353319.truvolley.volleyball_matches` 
    '''
    with BigQueryWarehouse.load("truvolley", validate=False) as warehouse:
        operation = query
        result = warehouse.fetch_all(operation)

    past = [i[0] for i in result]
    # print(past)
    return past


def get_winners(tour_id):
    outcomes = []
    tournament = f'http://bvbinfo.com/Tournament.asp?ID={tour_id}&Process=Matches'
    page = requests.get(tournament)
    soup = BeautifulSoup(page.content, "html.parser")
    results = soup.find_all('td')
    for result in results:
        # print('results')
        # print(result.text)
        if 'Match' in result.text:
            matches = result.text
            matches = matches.split('Match')
            # print(matches)
            games = []
            for match in matches:
                match = match.replace('\r\n\xa0\xa0\xa0\xa0\xa0\n','')
                match = match.replace('\n','')
                match = match.replace('\r','')
                if match.startswith(' '):
                    games.append(match)
                    # print(match)

    for game in games:
        # print(game)
        winners = game[game.find(':')+1:game.find('(')]
        winners = winners.strip().split(' / ')
        losers = game[game.find('f.')+2:game.find('(',game.find('(')+2)]
        losers = losers.strip().split(' / ')
        # print(winners)
        # print(losers)
        # print([tour_id]+winners+losers)
        outcomes.append([tour_id]+winners+losers)
    # print(outcomes)
    return outcomes

@task
def avp_data(tournaments):
    # tournaments = get_avp_tournaments(year)
    results = []
    for tournament in tournaments:
        try:
            results.append(get_winners(tournament))
        except Exception as e:
            print(f'tournament {tournament} had no matches : {e}')
    return results

current_year = datetime.date.today().year

@flow
def import_avp_matches(year=current_year):
    tournaments = get_avp_tournaments(year)
    print(tournaments)
    avp = avp_data(tournaments)
    for tournament in avp:
        for match in tournament:
            query = f'''
               insert `truvolley.volleyball_matches` (tournament_id,winner_1,winner_2,loser_1,loser_2)
               values({match[0]},"{match[1]}","{match[2]}","{match[3]}","{match[4]}")
               '''
            print(query)

            with BigQueryWarehouse.load("truvolley", validate=False) as warehouse:
                operation = query
                warehouse.execute(operation)

import_avp_matches()
