import pandas as pd
import os
import json

from utils import apply_linear_rate, reindex_mi, add_level


def dict2series(item_dict):
    """Return pd.Series from a dict containing val and index attributess.
    """
    if len(item_dict['index']) == 1:
        ds = pd.Series(item_dict['val'])
    elif len(item_dict['index']) == 2:
        ds = {(outerKey, innerKey): values for outerKey, innerDict in item_dict['val'].items() for
              innerKey, values in innerDict.items()}
        ds = pd.Series(ds)
    else:
        raise ValueError('More than 2 MultiIndex is not yet developed')
    ds.index.set_names(item_dict['index'], inplace=True)
    return ds


def json2miindex(json_dict):
    """Parse dict and returns pd.Series or pd.DataFrame.

    Parameters
    ----------
    json_dict: dict

    Returns
    -------
    pd.Series, pd.DataFrame
    """

    if isinstance(json_dict, float) or isinstance(json_dict, int) or isinstance(json_dict, str) or isinstance(json_dict,
                                                                                                              list) or json_dict is None:
        return json_dict
    if json_dict['type'] == 'pd.Series':
        return dict2series(json_dict)
    elif json_dict['type'] == 'pd.DataFrame':
        column_name = json_dict['index'][1]
        ds = dict2series(json_dict)
        return ds.unstack(column_name)
    elif json_dict['type'] == 'float' or json_dict['type'] == 'int':
        return json_dict['val']
    elif json_dict['type'] == 'file':
        pass
    else:
        print('Need to be done!!')


def parse_json(n_file):
    """Parse json file and return dict.

    For each primary key of json file assign:
    - float, int, str, list
    - MultiIndex pd.Series or pd.DataFrame thanks to json2miindex
    - dict to reapply the function

    Parameters
    ----------
    n_file: str
    Path to json file.

    Returns
    -------
    dict
    """
    result_dict = {}
    with open(n_file) as f:
        f_dict = json.load(f)
        for key, item in f_dict.items():
            if isinstance(item, float) or isinstance(item, int) or isinstance(item, str) or isinstance(item,
                                                                                                       list) or item is None:
                result_dict[key] = item
            elif isinstance(item, dict):
                if item['type'] == 'dict':
                    result_dict[key] = item
                elif item['type'] == 'pd.Series' or item['type'] == 'pd.DataFrame':
                    result_dict[key] = json2miindex(item)
                elif item['type'] == 'dict_to_parse':
                    r_dict = {}
                    for sub_key in [sub_k for sub_k in item.keys() if sub_k != 'type']:
                        r_dict[sub_key] = json2miindex(item[sub_key])
                    result_dict[key] = r_dict
    return result_dict


def final2consumption(consumption, conversion):
    """Conversion of primary consumption to final consumption.
    """
    consumption = pd.concat([consumption] * len(conversion.index),
                            keys=conversion.index, names=conversion.index.names)
    conversion = reindex_mi(conversion, consumption.index, conversion.index.names)
    return consumption * conversion


def population_housing_dynamic(pop_housing_prev, pop_housing_min, pop_housing_ini, factor):
    """Returns number of people by building for year.

    Number of people by housing decrease over the time.

    Parameters
    ----------
    pop_housing_prev: int
    pop_housing_min: int
    pop_housing_ini: int
    factor: int

    Returns
    -------
    int
    """
    eps_pop_housing = (pop_housing_prev - pop_housing_min) / (
            pop_housing_ini - pop_housing_min)
    eps_pop_housing = max(0, min(1, eps_pop_housing))
    factor_pop_housing = factor * eps_pop_housing
    return max(pop_housing_min, pop_housing_prev * (1 + factor_pop_housing))


def forecast2myopic(forecast_price, yr):
    """Returns myopic prices based on forecast prices and a year.
    """
    val = forecast_price.loc[:, yr]
    columns_year = forecast_price.columns[forecast_price.columns >= yr]
    myopic = pd.concat([val] * len(columns_year), axis=1)
    myopic.columns = columns_year
    myopic.index.set_names('Heating energy', inplace=True)
    return myopic


def parse_building_stock(config):
    """
    Parses and returns building stock and attributes to match Res-IRF input requirement.

    Parameters
    ----------
    config: dict

    Returns
    -------
    stock_ini : pd.Series
        Initial buildings stock. Attributes are stored as MultiIndex.
    attributes :  dict
        Multiple information regarding stock attributes.
        All values that could possibly taken buildings attributes.
        Conversion of attributes in numerical values (energy performance certificate, etc...).
    """

    # 1. Read building stock data

    name_file = os.path.join(os.getcwd(), config['stock_buildings']['source'])
    stock_ini = pd.read_pickle(name_file)
    stock_ini = stock_ini.reorder_levels(
        ['Occupancy status', 'Housing type', 'Income class', 'Heating energy', 'Energy performance', 'Income class owner'])

    # 2. Numerical value of stock attributes

    calibration_year = config['stock_buildings']['year']
    # years for input time series
    # maximum investment horizon is 30 years and model horizon is 2040. Input must be extended at least to 2070.
    last_year = 2080
    index_input_year = range(calibration_year, last_year + 1, 1)

    name_file = os.path.join(os.getcwd(), config['attributes']['source'])
    attributes = parse_json(name_file)

    attributes['attributes2income'] = attributes['attributes2income'].apply(apply_linear_rate, args=(
        config['Household income rate'], index_input_year))
    attributes['attributes2consumption_heater'] = attributes['attributes2primary_consumption'] * attributes[
        'attributes2heater']
    attributes['attributes2consumption'] = final2consumption(attributes['attributes2consumption_heater'],
                                                             attributes['attributes2final_energy'] ** -1)
    attributes['attributes2consumption_heater_construction'] = attributes[
                                                                   'attributes2primary_consumption_construction'] * \
                                                               attributes[
                                                                   'attributes2heater_construction']
    attributes['attributes2consumption_construction'] = final2consumption(
        attributes['attributes2consumption_heater_construction'],
        attributes['attributes2final_energy'] ** -1)

    # function of config
    attributes2horizon = dict()
    attributes['attributes2horizon_heater'] = attributes['attributes2horizon_heater'][config['green_value']]
    attributes['attributes2horizon_envelope'] = attributes['attributes2horizon_envelope'][config['green_value']]
    attributes2horizon[('Energy performance',)] = attributes['attributes2horizon_envelope']
    attributes2horizon[('Heating energy',)] = attributes['attributes2horizon_heater']
    attributes['attributes2horizon'] = attributes2horizon

    attributes['attributes2discount'] = attributes['attributes2discount'][config['budget_constraint']]

    file_dict = attributes['attributes_dict']
    keys = ['Housing type', 'Occupancy status', 'Heating energy', 'Energy performance', 'Income class']
    attributes['housing_stock_renovated'] = {key: file_dict[key] for key in keys}
    attributes['housing_stock_renovated']['Income class owner'] = file_dict['Income class']

    keys = ['Housing type', 'Occupancy status', 'Heating energy', 'Energy performance construction', 'Income class']
    attributes['housing_stock_constructed'] = {key: file_dict[key] for key in keys}
    attributes['housing_stock_constructed']['Income class owner'] = file_dict['Income class']
    attributes['housing_stock_constructed']['Energy performance'] = file_dict['Energy performance construction']
    attributes['housing_stock_constructed'].pop('Energy performance construction')

    return stock_ini, attributes


def parse_exogenous_input(folder, config):
    """Parses prices and costs input to match Res-IRF input requirement.

    Parameters
    ----------
    folder : str
    config : dict

    Returns
    -------
    energy_prices : pd.DataFrame
    energy_taxes : pd.DataFrame
    cost_invest : dict
        Keys are transition cost_envelope = cost_invest(tuple([Energy performance]).
    cost_invest_construction : dict
    co2_content : pd.DataFrame
    policies : dict
    summary_input: pd.DataFrame
    """

    calibration_year = config['stock_buildings']['year']
    last_year = 2080

    name_file = os.path.join(os.getcwd(), config['policies']['source'])
    policies = parse_json(name_file)

    carbon_tax = pd.read_csv(os.path.join(os.getcwd(), config['carbon_tax_value']['source']), index_col=[0])
    carbon_tax = carbon_tax.T
    carbon_tax.index.set_names('Heating energy', inplace=True)
    policies['carbon_tax']['value'] = carbon_tax

    # cost_invest
    cost_invest = dict()
    name_file = os.path.join(os.getcwd(), config['cost_renovation']['source'])
    cost_envelope = pd.read_csv(name_file, sep=',', header=[0], index_col=[0])
    cost_envelope.index.set_names('Energy performance', inplace=True)
    cost_envelope.columns.set_names('Energy performance final', inplace=True)
    cost_envelope = cost_envelope * (1 + 0.1) / (1 + 0.055)
    cost_invest['Energy performance'] = cost_envelope

    name_file = os.path.join(os.getcwd(), config['cost_switch_fuel']['source'])
    cost_switch_fuel = pd.read_csv(name_file, index_col=[0], header=[0])
    cost_switch_fuel.index.set_names('Heating energy', inplace=True)
    cost_switch_fuel.columns.set_names('Heating energy final', inplace=True)
    cost_switch_fuel = cost_switch_fuel * (1 + 0.1) / (1 + 0.055)
    cost_invest['Heating energy'] = cost_switch_fuel

    cost_invest_construction = dict()
    name_file = os.path.join(os.getcwd(), config['cost_construction']['source'])
    cost_construction = pd.read_csv(os.path.join(folder, name_file), sep=',', header=[0, 1], index_col=[0])
    cost_construction.index.set_names('Housing type', inplace=True)
    cost_invest_construction['Energy performance'] = cost_construction
    cost_invest_construction['Heating energy'] = None

    name_file = os.path.join(os.getcwd(), config['energy_prices_bt']['source'])
    energy_prices_bt = pd.read_csv(name_file, index_col=[0], header=[0]).T
    energy_prices_bt.index.set_names('Heating energy', inplace=True)
    energy_prices = energy_prices_bt

    # initialize energy taxes
    energy_taxes = energy_prices.copy()
    for col in energy_prices.columns:
        energy_taxes[col].values[:] = 0

    if config['energy_taxes']['vta']:
        vta = pd.Series([0.16, 0.16, 0.2, 0.2], index=['Power', 'Natural gas', 'Oil fuel', 'Wood fuel'])
        vta.index.set_names('Heating energy', inplace=True)
        vta_energy = (energy_prices_bt.T * vta).T
        energy_prices = energy_prices + vta_energy
        energy_taxes = energy_taxes + vta_energy

    if config['energy_taxes']['activated']:
        name_file = os.path.join(os.getcwd(), config['energy_taxes']['source'])
        energy_tax = pd.read_csv(name_file, index_col=[0], header=[0]).T
        energy_tax.index.set_names('Heating energy', inplace=True)

        # energy prices before cee and carbon tax and after vta and other energy taxes
        energy_prices = energy_prices + energy_tax
        energy_taxes = energy_taxes + energy_tax

    # extension of energy_prices time series
    last_year_prices = energy_prices.columns[-1]
    if last_year > last_year_prices:
        add_yrs = range(last_year_prices + 1, last_year + 1, 1)
        temp = pd.concat([energy_prices.loc[:, last_year_prices]] * len(add_yrs), axis=1)
        temp.columns = add_yrs
        energy_prices = pd.concat((energy_prices, temp), axis=1)

    if config['energy_prices_evolution'] == 'forecast':
        energy_prices = energy_prices.loc[:, calibration_year:]
    elif config['energy_prices_evolution'] == 'constant':
        energy_prices = pd.Series(energy_prices.loc[:, calibration_year], index=energy_prices.index)
        energy_prices.index.set_names('Heating energy', inplace=True)
        idx_yrs = range(calibration_year, last_year + 1, 1)
        energy_prices = pd.concat([energy_prices] * len(idx_yrs), axis=1)
        energy_prices.columns = idx_yrs
    else:
        raise ValueError("energy_prices_evolution should be 'forecast' or 'constant'")

    name_file = os.path.join(os.getcwd(), config['co2_content']['source'])
    co2_content = pd.read_csv(name_file, index_col=[0], header=[0]).T
    co2_content.index.set_names('Heating energy', inplace=True)

    # extension of co2_content time series
    last_year_prices = co2_content.columns[-1]
    if last_year > last_year_prices:
        add_yrs = range(last_year_prices + 1, last_year + 1, 1)
        temp = pd.concat([co2_content.loc[:, last_year_prices]] * len(add_yrs), axis=1)
        temp.columns = add_yrs
        co2_content = pd.concat((co2_content, temp), axis=1)

    co2_content = co2_content.loc[:, calibration_year:]

    summary_input = dict()

    summary_input['Power prices bt (€/kWh)'] = energy_prices_bt.loc['Power', :]
    summary_input['Natural gas prices bt (€/kWh)'] = energy_prices_bt.loc['Natural gas', :]
    summary_input['Oil fuel prices bt (€/kWh)'] = energy_prices_bt.loc['Oil fuel', :]
    summary_input['Wood fuel prices bt (€/kWh)'] = energy_prices_bt.loc['Wood fuel', :]

    summary_input['Power prices (€/kWh)'] = energy_prices.loc['Power', :]
    summary_input['Natural gas prices (€/kWh)'] = energy_prices.loc['Natural gas', :]
    summary_input['Oil fuel prices (€/kWh)'] = energy_prices.loc['Oil fuel', :]
    summary_input['Wood fuel prices (€/kWh)'] = energy_prices.loc['Wood fuel', :]

    summary_input['Power emission (gCO2/kWh)'] = co2_content.loc['Power', :]
    summary_input['Natural gas emission (gCO2/kWh)'] = co2_content.loc['Natural gas', :]
    summary_input['Oil fuel emission (gCO2/kWh)'] = co2_content.loc['Oil fuel', :]
    summary_input['Wood fuel (gCO2/kWh)'] = co2_content.loc['Wood fuel', :]

    summary_input = pd.DataFrame(summary_input)
    summary_input = summary_input.loc[calibration_year:, :]

    return energy_prices, energy_taxes, cost_invest, cost_invest_construction, co2_content, policies, summary_input


def parse_parameters(folder, config, stock_sum):
    """Parse input that are not implicitly subject to a scenario.

    Parameters
    ----------
    folder : str
        Folder where to look for input files.
    config: dict
    stock_sum : float
        Number of buildings in stock data.

    Returns
    -------
    parameters : dict
        Mainly contains demographic and macro-economic variables. Also contains function parameter (lbd).
    summary_param: pd.DataFrame
    """

    # years for input time series
    calibration_year = config['stock_buildings']['year']

    last_year = 2080
    index_input_year = range(calibration_year, last_year + 1, 1)

    # 1. Parameters

    name_file = os.path.join(os.getcwd(), config['parameters']['source'])
    parameters = parse_json(name_file)

    # 2. Demographic and macro-economic variable
    parameters['Calibration consumption'] = parameters['Aggregated consumption coefficient {}'.format(calibration_year)]

    name_file = os.path.join(os.getcwd(), config['population']['source'])
    parameters['Population total'] = pd.read_csv(os.path.join(folder, name_file), sep=',', header=None,
                                                 index_col=[0],
                                                 squeeze=True)
    # sizing_factor < 1 --> all extensive results are calibrated by the size of the initial parc
    sizing_factor = stock_sum / parameters['Stock total ini {}'.format(calibration_year)]
    parameters['Sizing factor'] = sizing_factor
    parameters['Population'] = parameters['Population total'] * sizing_factor

    parameters['Available income'] = apply_linear_rate(parameters['Available income ini {}'.format(calibration_year)],
                                                       parameters['Available income rate'], index_input_year)

    # inflation
    parameters['Price index'] = pd.Series(1, index=index_input_year)
    parameters['Available income real'] = parameters['Available income'] / parameters['Price index']
    parameters['Available income real population'] = parameters['Available income real'] / parameters[
        'Population total']

    population_housing_min = parameters['Population housing min']
    population_housing = dict()
    population_housing[calibration_year] = parameters['Population'].loc[calibration_year] / stock_sum
    max_year = max(parameters['Population'].index)

    stock_needed = dict()
    stock_needed[calibration_year] = parameters['Population'].loc[calibration_year] / population_housing[
        calibration_year]

    for year in index_input_year[1:]:
        if year > max_year:
            break
        population_housing[year] = population_housing_dynamic(population_housing[year - 1],
                                                              population_housing_min,
                                                              population_housing[calibration_year],
                                                              parameters['Factor population housing ini'])
        stock_needed[year] = parameters['Population'].loc[year] / population_housing[year]

    parameters['Population housing'] = pd.Series(population_housing)
    parameters['Stock needed'] = pd.Series(stock_needed)

    # 5. Others

    parameters['Renovation rate max'] = parameters['Renovation rate max {}'.format(calibration_year)]

    proba_performance = parameters['Probability disease performance']
    proba_income = parameters['Probability disease income {}'.format(calibration_year)]

    proba_performance = add_level(proba_performance, proba_income.index, axis=0)
    proba_income = reindex_mi(proba_income, proba_performance.index)
    parameters['Probability disease'] = proba_performance * proba_income
    parameters['Cost disease'] = apply_linear_rate(parameters['Cost disease'], parameters['Cost disease rate'],
                                                   index_input_year)

    # 6. Summary

    summary_param = dict()
    summary_param['Total population (Millions)'] = parameters['Population'] / 10**6
    summary_param['Income (Billions €)'] = parameters['Available income real'] * sizing_factor / 10**9
    summary_param['Buildings stock (Millions)'] = pd.Series(stock_needed) / 10**6
    summary_param['Person by housing'] = pd.Series(population_housing)
    summary_param = pd.DataFrame(summary_param)
    summary_param = summary_param.loc[calibration_year:, :]

    return parameters, summary_param


def parse_observed_data(config):
    """Parses and returns observed data to match Res-IRF input requirement.

    Parameters
    ----------
    config: dict

    Returns
    -------
    rate_renovation_ini : pd.DataFrame
        Observed renovation rate in calibration year.
    ms_renovation_ini : pd.DataFrame
        Observed market share in calibration year.
    ms_construction_ini : pd.DataFrame
        Observed market share in calibration year.
    """

    name_file = os.path.join(os.getcwd(), config['renovation_rate_ini']['source'])
    renovation_rate_ini = pd.read_csv(name_file, header=[0], squeeze=True)
    columns = list(renovation_rate_ini.columns[:renovation_rate_ini.shape[1] - 1])
    renovation_rate_ini = renovation_rate_ini.set_index(columns).iloc[:, 0]

    name_file = os.path.join(os.getcwd(), config['ms_renovation_ini']['source'])
    ms_renovation_ini = pd.read_csv(name_file, index_col=[0], header=[0])
    ms_renovation_ini.index.set_names(['Energy performance'], inplace=True)
    ms_renovation_ini.columns.set_names(['Energy performance final'], inplace=True)

    name_file = os.path.join(os.getcwd(), config['ms_construction_ini']['source'])
    ms_construction_ini = pd.read_csv(name_file, index_col=[0, 1], header=[0, 1])
    ms_construction_ini.index.set_names(['Occupancy status', 'Housing type'], inplace=True)

    return renovation_rate_ini, ms_renovation_ini, ms_construction_ini


