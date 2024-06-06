import os
import arcpy
import argparse
import configparser
import time

def ebkrigingmodel(year, base_path, kriging_params):
    arcpy.env.overwriteOutput = True

    # Resolve the base_path to an absolute path
    base_path = os.path.abspath(base_path)

    data_path = os.path.join(base_path, "data")
    gdb_path = os.path.join(base_path, "kriging.gdb")
    output_path = os.path.join(base_path, "output")
    
    DTW_csv = os.path.join(data_path, f"DTW{year}.csv")

    # Create the geodatabase if it does not exist
    if not arcpy.Exists(gdb_path):
        arcpy.management.CreateFileGDB(base_path, "kriging.gdb")

    DTWPoint = os.path.join(gdb_path, "DTWPoint")
    retry_count = 5
    while retry_count > 0:
        try:
            arcpy.management.XYTableToPoint(in_table=DTW_csv, out_feature_class=DTWPoint, x_field="X", y_field="Y", z_field="DTW_BGS", coordinate_system="PROJCS[\"NAD_1983_UTM_Zone_11N\",GEOGCS[\"GCS_North_American_1983\",DATUM[\"D_North_American_1983\",SPHEROID[\"GRS_1980\",6378137.0,298.257222101]],PRIMEM[\"Greenwich\",0.0],UNIT[\"Degree\",0.0174532925199433]],PROJECTION[\"Transverse_Mercator\"],PARAMETER[\"False_Easting\",500000.0],PARAMETER[\"False_Northing\",0.0],PARAMETER[\"Central_Meridian\",-117.0],PARAMETER[\"Scale_Factor\",0.9996],PARAMETER[\"Latitude_Of_Origin\",0.0],UNIT[\"Meter\",1.0]];-5120900 -9998100 450445547.391054;-100000 10000;-100000 10000;0.001;0.001;0.001;IsHighPrecision")
            break
        except arcpy.ExecuteError as e:
            if "ERROR 000464" in str(e):
                retry_count -= 1
                print(f"Schema lock error encountered. Retrying {retry_count} more times...")
                time.sleep(5)
            else:
                raise

    DTW_BGS_gs = "DTW_BGS_gs"
    DTW_BGS_raster = os.path.join(gdb_path, f"DTW_BGS_{year}")

    if arcpy.Exists(DTW_BGS_raster):
        overwrite = input(f"The raster for the year {year} already exists. Do you want to overwrite it? (yes/no): ")
        if overwrite.lower() != 'yes':
            print(f"Skipping processing for the year {year}.")
            return

    search_neighborhood = kriging_params['search_neighborhood'].replace(";", " ")

    probability_threshold = kriging_params['probability_threshold']
    if probability_threshold is None or probability_threshold.lower() == 'none':
        probability_threshold = None

    with arcpy.EnvManager(outputCoordinateSystem="PROJCS[\"NAD_1983_UTM_Zone_11N\",GEOGCS[\"GCS_North_American_1983\",DATUM[\"D_North_American_1983\",SPHEROID[\"GRS_1980\",6378137.0,298.257222101]],PRIMEM[\"Greenwich\",0.0],UNIT[\"Degree\",0.0174532925199433]],PROJECTION[\"Transverse_Mercator\"],PARAMETER[\"False_Easting\",500000.0],PARAMETER[\"False_Northing\",0.0],PARAMETER[\"Central_Meridian\",-117.0],PARAMETER[\"Scale_Factor\",0.9996],PARAMETER[\"Latitude_Of_Origin\",0.0],UNIT[\"Meter\",1.0]]"):
        arcpy.ga.EmpiricalBayesianKriging(
            in_features=DTWPoint,
            z_field="DTW_BGS",
            out_ga_layer=DTW_BGS_gs,
            out_raster=DTW_BGS_raster,
            cell_size=kriging_params['cell_size'],
            transformation_type=kriging_params['transformation_type'],
            max_local_points=kriging_params['max_local_points'],
            overlap_factor=kriging_params['overlap_factor'],
            number_semivariograms=kriging_params['number_semivariograms'],
            search_neighborhood=search_neighborhood,
            output_type=kriging_params['output_type'],
            quantile_value=kriging_params['quantile_value'],
            threshold_type=kriging_params['threshold_type'],
            probability_threshold=probability_threshold,
            semivariogram_model_type=kriging_params['semivariogram_model_type']
        )
        DTW_BGS_raster = arcpy.Raster(DTW_BGS_raster)

    geotiff_path = os.path.join(output_path, f"DTW_BGS_{year}.tif")
    if os.path.exists(geotiff_path):
        overwrite = input(f"The GeoTIFF for the year {year} already exists. Do you want to overwrite it? (yes/no): ")
        if overwrite.lower() != 'yes':
            print(f"Skipping GeoTIFF export for the year {year}.")
            return

    arcpy.management.CopyRaster(in_raster=DTW_BGS_raster, out_rasterdataset=geotiff_path, format="TIFF")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run kriging model for a specified year or range of years")
    parser.add_argument('--config', type=str, default='config.ini', help='Path to the configuration file')
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Configuration file not found: {args.config}")
        exit(1)

    print(f"Reading configuration from {args.config}")
    config = configparser.ConfigParser()
    config.read(args.config)

    base_path = os.path.abspath(config.get('settings', 'base_path'))

    kriging_params = {
        'cell_size': config.get('kriging_parameters', 'cell_size'),
        'transformation_type': config.get('kriging_parameters', 'transformation_type'),
        'max_local_points': config.getint('kriging_parameters', 'max_local_points'),
        'overlap_factor': config.getfloat('kriging_parameters', 'overlap_factor'),
        'number_semivariograms': config.getint('kriging_parameters', 'number_semivariograms'),
        'search_neighborhood': config.get('kriging_parameters', 'search_neighborhood'),
        'output_type': config.get('kriging_parameters', 'output_type'),
        'quantile_value': config.getfloat('kriging_parameters', 'quantile_value'),
        'threshold_type': config.get('kriging_parameters', 'threshold_type'),
        'probability_threshold': config.get('kriging_parameters', 'probability_threshold'),
        'semivariogram_model_type': config.get('kriging_parameters', 'semivariogram_model_type')
    }

    years = config.get('settings', 'years').strip()

    if '-' in years:
        start_year, end_year = map(int, years.split('-'))
        year_list = range(start_year, end_year + 1)
    elif ',' in years:
        year_list = [int(year) for year in years.split(',')]
    else:
        year_list = [int(years)]

    with arcpy.EnvManager(scratchWorkspace=os.path.join(base_path, "kriging.gdb"), workspace=os.path.join(base_path, "kriging.gdb")):
        for year in year_list:
            ebkrigingmodel(year, base_path, kriging_params)
