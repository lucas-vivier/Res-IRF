"""
Res-IRF script
--------------


This script requires that 'pandas' be installed within the Python
environment you are running this script in.
"""

import os
import time
import pandas as pd
from copy import deepcopy
from shutil import copyfile
from itertools import product

from buildings import HousingStock, HousingStockRenovated, HousingStockConstructed
from policies import EnergyTaxes, Subsidies, RegulatedLoan, RenovationObligation, SubsidiesRecyclingTax, ThermalRegulation
from parse_output import parse_output


def res_irf(calibration_year, end_year, folder, config, parameters, policies_parameters, attributes, energy_prices_bp,
            energy_taxes, cost_invest, cost_invest_construction, cost_switch_fuel_end, stock_ini, co2_tax, co2_emission,
            rate_renovation_ini, ms_renovation_ini, ms_construction_ini, income_tenants_construction, logging,
            output_detailed):
    """Res-IRF model main function.

    Res-IRF is a multi-agent building stock dynamic microsimulation model.
    1. Loading public policies
    2. Calculating energy taxes and energy prices
    3. Initializing HousingStockRenovated and HousingStockConstructed object
    4. Calibration of intangible cost (to match initial market share) and renovation function parameters
    5. Iteration over the years of building stock dynamics:
        - Demolition,
        - Renovation,
        - Construction,
        - Considering learning-by-doing and information acceleration.

    Parameters
    ----------
    calibration_year: int
        Initial year when non observables parameters are calibrated.
    folder: dict
        Path to a scenario-specific folder used to store all outputs.
    end_year: int
        Final simulation year.
    config: dict
        Dictionary with all scenarios configurations parameters.
    parameters: dict
        Dictionary with parameters.
    policies_parameters: dict
        Dictionary with all policies parameters.
    attributes: dict
        Specific dictionary setting up numerical values for each stock attribute.
        Attributes also contain a list of each attribute.
    energy_prices_bp: pd.DataFrame
        After VTA and other energy taxes but before any endogenous energy taxes.
    energy_taxes: pd.DataFrame
        Exogenous energy taxes.
    cost_invest: dict
        Investment cost for transition.
    cost_invest_construction: dict
        Construction cost.
    cost_switch_fuel_end: pd.DataFrame
    stock_ini: pd.Series
        Initial stock.
    co2_tax: pd.DataFrame
        CO2 content used to calculate tax cost.
    co2_emission: pd.DataFrame
        CO2 content used to calculate emission saving.
    rate_renovation_ini: pd.Series
        Renovation rate to match during calibration year.
    ms_renovation_ini: pd.DataFrame
        Market share between renovation option to match during calibration year.
    ms_construction_ini: pd.DataFrame
        Market share between construction option to match during calibration year.
    income_tenants_construction: pd.Series
        Income tenant of agent.
    logging:
    output_detailed: bool
    """

    start = time.time()

    logging.debug('Creation of output folder: {}'.format(folder['output']))

    # copyfile(os.path.join(folder['input'], scenario_file), os.path.join(folder['output'], scenario_file))
    pd.Series(config).to_csv(os.path.join(folder['output'], 'scenario.csv'))
    copyfile(config['parameters']['source'], os.path.join(folder['output'], 'parameters.json'))

    output = dict()
    logging.debug('Loading in output_dict all input needed for post-script analysis')

    output['Population total'] = parameters['Population total']
    output['Population'] = parameters['Population']
    # output['Population housing'] = parameters['Population housing']
    output['Stock needed'] = parameters['Stock needed']
    output['Cost envelope'] = dict()
    output['Cost envelope'][calibration_year] = cost_invest['Energy performance']
    output['Cost construction'] = dict()
    output['Cost construction'][calibration_year] = cost_invest_construction['Energy performance']

    logging.debug('Initialization')

    logging.debug('Initialize public policies')
    subsidies_dict = {}
    energy_taxes_dict = {}
    renovation_obligation_dict = {}
    thermal_regulation_construction = None
    thermal_regulation_renovation = None
    for pol, item in policies_parameters.items():
        if item['name'] in config.keys() and config[item['name']]['activated']:
            logging.debug('Considering: {}'.format(pol))
            if item['policy'] == 'subsidies':
                subsidies_dict[pol] = Subsidies(item['name'], config[item['name']]['start'],
                                                config[item['name']]['end'], item['unit'], item['value'],
                                                transition=item['transition'],
                                                calibration=config[item['name']]['calibration'],
                                                time_dependent=item['time_dependent'],
                                                targets=item['targets'],
                                                cost_max=item['cost_max'],
                                                cost_min=item['cost_min'],
                                                subsidy_max=item['subsidy_max'],
                                                priority=item['priority'],
                                                area=attributes['attributes2area'])

            elif item['policy'] == 'energy_taxes':
                energy_taxes_dict[pol] = EnergyTaxes(item['name'], config[item['name']]['start'],
                                                     config[item['name']]['end'], item['unit'],
                                                     item['value'],
                                                     calibration=config[item['name']]['calibration'])

            elif item['policy'] == 'regulated_loan':
                subsidies_dict[pol] = RegulatedLoan(item['name'], config[item['name']]['start'],
                                                    config[item['name']]['end'],
                                                    ir_regulated=item['ir_regulated'], ir_market=item['ir_market'],
                                                    principal_min=item['principal_min'],
                                                    principal_max=item['principal_max'],
                                                    horizon=item['horizon'], targets=item['targets'],
                                                    transition=item['transition'],
                                                    calibration=config[item['name']]['calibration'])
                subsidies_dict[pol].reindex_attributes(stock_ini.index)

            elif item['policy'] == 'renovation_obligation':
                renovation_obligation_dict[pol] = RenovationObligation(item['name'], item['start_targets'],
                                                                       participation_rate=item['participation_rate'],
                                                                       columns=range(calibration_year, 2081, 1),
                                                                       calibration=config[item['name']]['calibration'])

            elif item['policy'] == 'subsidy_tax':
                subsidy_tax = SubsidiesRecyclingTax(item['name'], config[item['name']]['start'],
                                                    config[item['name']]['end'], item['tax_unit'],
                                                    item['tax_value'], item['subsidy_unit'],
                                                    subsidy_value=item['subsidy_value'],
                                                    calibration=config[item['name']]['calibration'])
                subsidies_dict[pol] = subsidy_tax
                energy_taxes_dict[pol] = subsidy_tax

            elif item['policy'] == 'thermal_regulation_construction':
                thermal_regulation_construction = ThermalRegulation(item['name'],
                                                                    config[item['name']]['start'],
                                                                    config[item['name']]['end'],
                                                                    item['targets'], item['transition']
                                                                    )

            elif item['policy'] == 'thermal_regulation_renovation':
                thermal_regulation_renovation = ThermalRegulation(item['name'],
                                                                  config[item['name']]['start'],
                                                                  config[item['name']]['end'],
                                                                  item['targets'], item['transition']
                                                                  )

    subsidies = list(subsidies_dict.values())
    # reorder subsidies to let priority first
    subsidies = [s for s in subsidies if s.priority is True] + [s for s in subsidies if s.priority is False]

    energy_taxes_detailed = dict()
    energy_taxes_detailed['energy_taxes'] = energy_taxes
    total_taxes = None
    for _, tax in energy_taxes_dict.items():
        val = tax.price_to_taxes(energy_prices=energy_prices_bp, co2_content=co2_tax)
        # if not indexed by heating energy
        if isinstance(val, pd.Series):
            val = pd.concat([val] * len(attributes['housing_stock_renovated']['Heating energy']), axis=1).T
            val.index = attributes['housing_stock_renovated']['Heating energy']
            val.index.set_names(['Heating energy'], inplace=True)

        if total_taxes is None:
            total_taxes = val
        else:
            yrs = total_taxes.columns.union(val.columns)
            total_taxes = total_taxes.reindex(yrs, axis=1).fillna(0) + val.reindex(yrs, axis=1).fillna(0)

        energy_taxes_detailed[tax.name] = val

    if total_taxes is not None:
        temp = total_taxes.reindex(energy_prices_bp.columns, axis=1).fillna(0)
        energy_prices = energy_prices_bp + temp
        energy_taxes = energy_taxes + temp
    else:
        energy_prices = energy_prices_bp

    logging.debug('Creating HousingStockRenovated Python object')
    buildings = HousingStockRenovated(stock_ini, attributes['housing_stock_renovated'], calibration_year,
                                      attributes2area=attributes['attributes2area'],
                                      attributes2horizon=attributes['attributes2horizon'],
                                      attributes2discount=attributes['attributes2discount'],
                                      attributes2income=attributes['attributes2income'],
                                      attributes2consumption=attributes['attributes2consumption'],
                                      residual_rate=parameters['Residual destruction rate'],
                                      destruction_rate=parameters['Destruction rate'],
                                      rate_renovation_ini=rate_renovation_ini,
                                      learning_year=parameters['Learning years renovation'],
                                      npv_min=parameters['NPV min'],
                                      rate_max=parameters['Renovation rate max'],
                                      rate_min=parameters['Renovation rate min'],
                                      kwh_cumac_transition=attributes['kwh_cumac_transition'])

    logging.debug('Initialize energy consumption and cash-flows')
    buildings.ini_energy_cash_flows(energy_prices)
    # io_share_seg = buildings.to_io_share_seg()
    stock_area_existing = buildings.stock_area

    logging.debug('Creating HousingStockConstructed Python object')
    segments_construction = pd.MultiIndex.from_tuples(list(product(*[v for _, v in attributes['housing_stock_constructed'].items()])))
    segments_construction.names = [k for k in attributes['housing_stock_constructed'].keys()]
    buildings_constructed = HousingStockConstructed(pd.Series(0, dtype='float64', index=segments_construction),
                                                    attributes['housing_stock_constructed'], calibration_year,
                                                    parameters['Stock needed'],
                                                    share_multi_family=parameters['Share multi-family'],
                                                    os_share_ht=parameters['Occupancy status share housing type'],
                                                    tenants_income=income_tenants_construction,
                                                    stock_area_existing=stock_area_existing,
                                                    attributes2area=attributes['attributes2area_construction'],
                                                    attributes2horizon=attributes['attributes2horizon_construction'],
                                                    attributes2discount=attributes['attributes2discount_construction'],
                                                    attributes2income=attributes['attributes2income'],
                                                    attributes2consumption=attributes['attributes2consumption_construction'])

    # policies don't need to start and to end to be used during calibration
    subsidies_calibration = [policy for policy in subsidies if policy.calibration is True]

    cost_intangible_construction = None
    if config['cost_intangible_construction']['activated']:
        logging.debug('Calibration market share construction --> intangible cost construction')
        cost_intangible_construction = dict()
        name_file = config['cost_intangible_construction']['source']
        source = config['cost_intangible_construction']['source_type']
        if source == 'function':
            cost_intangible_construction['Energy performance'] = buildings_constructed.calibration_market_share(
                energy_prices,
                ms_construction_ini,
                cost_invest=cost_invest_construction,
                subsidies=subsidies_calibration)
            logging.debug('End of calibration and dumping: {}'.format(name_file))
            cost_intangible_construction['Energy performance'].to_pickle(name_file)
        elif source == 'file':
            logging.debug('Loading cost_intangible_construction from {}'.format(name_file))
            cost_intangible_construction['Energy performance'] = pd.read_pickle(name_file)

        cost_intangible_construction['Heating energy'] = None
        output['Cost intangible construction'] = dict()
        output['Cost intangible construction'][calibration_year] = cost_intangible_construction['Energy performance']

    cost_intangible = None
    if config['cost_intangible']['activated']:
        logging.debug('Calibration market share >>> intangible cost')
        cost_intangible = dict()
        name_file = config['cost_intangible']['source']
        source = config['cost_intangible']['source_type']
        if source == 'function':

            cost_intangible['Energy performance'], ms_calibration = buildings.calibration_market_share(energy_prices,
                                                                                                       ms_renovation_ini,
                                                                                                       cost_invest=cost_invest,
                                                                                                       consumption='conventional',
                                                                                                       subsidies=subsidies_calibration,
                                                                                                       option=config[
                                                                                                           'cost_intangible'][
                                                                                                           'option'])

            logging.debug('End of calibration and dumping: {}'.format(name_file))
            cost_intangible['Energy performance'].to_pickle(name_file)
            if ms_calibration is not None:
                ms_calibration.to_csv(os.path.join(folder['output'], 'ms_calibration.csv'))

        elif source == 'file':
            logging.debug('Loading intangible_cost from {}'.format(name_file))
            cost_intangible['Energy performance'] = pd.read_pickle(name_file)
            cost_intangible['Energy performance'].columns.set_names('Energy performance final', inplace=True)

        cost_intangible['Heating energy'] = None
        output['Cost intangible'] = dict()
        output['Cost intangible'][calibration_year] = cost_intangible['Energy performance']

    logging.debug('Calibration renovation rate >>> rho')
    name_file = config['rho']['source']
    source = config['rho']['source_type']
    if source == 'function':
        rho, renovation_rate_calibration = buildings.calibration_renovation_rate(energy_prices, rate_renovation_ini,
                                                                                 cost_invest=cost_invest,
                                                                                 cost_intangible=cost_intangible,
                                                                                 subsidies=subsidies_calibration,
                                                                                 option=config['rho']['option'])
        logging.debug('End of calibration and dumping: {}'.format(name_file))
        rho.to_pickle(name_file)

        if renovation_rate_calibration is not None:
            renovation_rate_calibration.to_csv(os.path.join(folder['output'], 'renovation_rate_calibration.csv'))

    elif source == 'file':
        logging.debug('Loading intangible_cost from {}'.format(name_file))
        rho = pd.read_pickle(name_file)
    else:
        rho = None
    buildings.rho = rho

    # calculate tax revenues to size recycled subsidy
    for _, tax in energy_taxes_dict.items():
        if tax.policy == 'subsidy_tax':
            val = tax.price_to_taxes(energy_prices=energy_prices_bp, co2_content=co2_tax).loc[:, calibration_year]

            consumption_new = buildings_constructed.to_consumption_actual(energy_prices).loc[:,
                              calibration_year] * buildings_constructed.stock * buildings_constructed.to_area()
            consumption = buildings.to_consumption_actual(energy_prices).loc[:,
                          calibration_year] * buildings.stock * buildings.to_area()
            consumption = pd.concat((consumption, consumption_new.reorder_levels(consumption.index.names)), axis=0)

            consumption = (consumption.groupby('Heating energy').sum().T * parameters['Calibration consumption']).T
            tax.tax_revenue[calibration_year] = (consumption * val).sum()
            # add buildings_constructed.energy_expenditure(val).sum()

    cost_switch_fuel_ini = None
    if cost_switch_fuel_end is not None:
        cost_switch_fuel_ini = cost_invest['Heating energy'].copy()

    years = range(calibration_year, end_year, 1)
    logging.debug('Launching iterations')

    for year in years[1:]:
        logging.debug('YEAR: {}'.format(year))

        buildings.year = year

        subsidies_year = [policy for policy in subsidies if policy.start <= year < policy.end]

        if thermal_regulation_construction is not None:
            buildings_constructed.attributes_values = thermal_regulation_construction.apply_regulation(
                deepcopy(buildings_constructed.total_attributes_values), year)

        if thermal_regulation_renovation is not None:
            buildings.attributes_values = thermal_regulation_renovation.apply_regulation(
                deepcopy(buildings.total_attributes_values), year)

        if cost_switch_fuel_end is not None:
            cost_invest['Heating energy'] = cost_switch_fuel_ini + (year - calibration_year) * (
                        cost_switch_fuel_end - cost_switch_fuel_ini) / (2012 - 1984)

        flow_demolition_sum = 0
        if parameters['Destruction rate'] > 0:
            logging.debug('Demolition dynamic')
            flow_demolition_seg = buildings.to_flow_demolition_seg()
            logging.debug('Demolition: {:,.0f} buildings, i.e.: {:.2f}%'.format(flow_demolition_seg.sum(),
                                                                                flow_demolition_seg.sum() / buildings.stock.sum() * 100))
            logging.debug('Update demolition')
            buildings.add_flow(- flow_demolition_seg)
            flow_demolition_sum = flow_demolition_seg.sum()

        logging.debug('Renovation dynamic')
        renovation_obligation = None
        if 'renovation_obligation' in renovation_obligation_dict:
            renovation_obligation = renovation_obligation_dict['renovation_obligation']
        flow_remained_seg, flow_area_renovation_seg = buildings.to_flow_remained(energy_prices,
                                                                                 consumption='conventional',
                                                                                 cost_invest=cost_invest,
                                                                                 cost_intangible=cost_intangible,
                                                                                 subsidies=subsidies_year,
                                                                                 renovation_obligation=renovation_obligation,
                                                                                 mutation=parameters['Mutation rate'],
                                                                                 rotation=parameters['Rotation rate']
                                                                                 )

        logging.debug('Updating stock segmented and renovation knowledge after renovation')
        buildings.update_stock(flow_remained_seg, flow_area_renovation_seg=flow_area_renovation_seg)

        if config['info_renovation'] and config['cost_intangible']['activated']:
            logging.debug('Information acceleration - renovation')
            cost_intangible['Energy performance'] = HousingStock.information_acceleration(buildings.knowledge,
                                                                                          output['Cost intangible'][
                                                                                              buildings.calibration_year],
                                                                                          parameters[
                                                                                              'Information rate max renovation'],
                                                                                          parameters[
                                                                                              'Learning information rate renovation'])
            output['Cost intangible'][year] = cost_intangible['Energy performance']

        if config['lbd_renovation']:
            logging.debug('Learning by doing - renovation')
            cost_invest['Energy performance'] = HousingStock.learning_by_doing(buildings.knowledge,
                                                                               output['Cost envelope'][
                                                                                   buildings.calibration_year],
                                                                               parameters[
                                                                                   'Learning by doing renovation'])
            output['Cost envelope'][year] = cost_invest['Energy performance']

        logging.debug('Construction dynamic')
        buildings_constructed.year = year
        flow_constructed = parameters['Stock needed'].loc[
                               year] - buildings.stock.sum() - buildings_constructed.stock.sum()
        logging.debug('Construction of: {:,.0f} buildings'.format(flow_constructed))
        buildings_constructed.flow_constructed = flow_constructed

        logging.debug('Updating attributes2area_construction')
        buildings_constructed.update_area_construction(parameters['Elasticity area construction'],
                                                       parameters['Available income real population'],
                                                       parameters['Area max construction'])
        logging.debug('Updating flow_constructed segmented')
        # update_flow_constructed_seg will automatically update area constructed and so construction knowledge
        if flow_constructed > 1:
            buildings_constructed.update_flow_constructed_seg(energy_prices,
                                                              cost_intangible=cost_intangible_construction,
                                                              cost_invest=cost_invest_construction,
                                                              nu=parameters['Nu construction'],
                                                              subsidies=None)

        if config['info_construction'] and config['cost_intangible_construction']['activated']:
            logging.debug('Information acceleration - construction')
            cost_intangible_construction['Energy performance'] = HousingStock.information_acceleration(
                buildings_constructed.knowledge,
                output['Cost intangible construction'][buildings_constructed.calibration_year],
                parameters['Information rate max construction'],
                parameters['Learning information rate construction'])
            output['Cost intangible construction'][year] = cost_intangible_construction['Energy performance']

        if config['lbd_construction']:
            logging.debug('Learning by doing - construction')
            cost_invest_construction['Energy performance'] = HousingStock.learning_by_doing(
                buildings_constructed.knowledge,
                output['Cost construction'][buildings_constructed.calibration_year],
                parameters['Learning by doing renovation'],
                cost_lim=parameters['Cost construction lim'])
            output['Cost construction'][year] = cost_invest_construction['Energy performance']

        logging.debug('Calculating tax revenue')

        for _, tax in energy_taxes_dict.items():
            if tax.policy == 'subsidy_tax':
                val = tax.price_to_taxes(energy_prices=energy_prices_bp, co2_content=co2_tax).loc[:, year]

                consumption_new = buildings_constructed.to_consumption_actual(energy_prices).loc[:,
                                  year] * buildings_constructed.stock * buildings_constructed.to_area()
                consumption = buildings.to_consumption_actual(energy_prices).loc[:,
                              year] * buildings.stock * buildings.to_area()
                consumption = pd.concat((consumption, consumption_new.reorder_levels(consumption.index.names)), axis=0)

                consumption = (consumption.groupby('Heating energy').sum().T * parameters['Calibration consumption']).T
                tax.tax_revenue[year] = (consumption * val).sum()

        logging.debug(
            '\nSummary:\nYear: {}\nStock after demolition: {:,.0f}\nDemolition: {:,.0f}\nNeeded: {:,.0f}\nRenovation: {:,.0f}\nConstruction: {:,.0f}'.format(
                year, buildings.stock.sum(), flow_demolition_sum, parameters['Stock needed'].loc[year],
                buildings.flow_renovation_label_energy_dict[year].sum().sum(), flow_constructed))

    parse_output(output, buildings, buildings_constructed, energy_prices, energy_taxes, energy_taxes_detailed,
                 co2_emission, parameters['Calibration consumption'], folder['output'],
                 lbd_output=False, output_detailed=output_detailed)

    end = time.time()
    logging.debug('Time for the module: {:,.0f} seconds.'.format(end - start))
    logging.debug('End')