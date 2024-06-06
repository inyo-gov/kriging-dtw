import arcpy
import os
import argparse
import configparser

def ensure_fields_exist(table, fields):
    existing_fields = [f.name for f in arcpy.ListFields(table)]
    for field in fields:
        if field['name'] not in existing_fields:
            arcpy.management.AddField(table, field['name'], field['type'])
            print(f"Added field {field['name']} of type {field['type']} to {table}")

def zonal_statistics(year, base_path, parcel_fc):
    # Define the paths
    gdb_path = os.path.join(base_path, "kriging.gdb")
    output_dir = os.path.join(base_path, "output", "zonal_stats")
    os.makedirs(output_dir, exist_ok=True)
    
    raster_path = os.path.join(gdb_path, f"DTW_BGS_{year}")
    parcel_db = os.path.join(gdb_path, f"parcel_dtw_stats_{year}")
    csv_path = os.path.join(output_dir, f"parcel_dtw_stats_{year}.csv")
    new_parcel_layer = os.path.join(gdb_path, f"vegetation_parcels_{year}")
    
    if not arcpy.Exists(raster_path):
        print(f"Raster for the year {year} does not exist. Skipping...")
        return

    if not arcpy.Exists(parcel_fc):
        print(f"Parcel feature class {parcel_fc} does not exist.")
        return
    
    # Check if PCL field exists
    fields = [f.name for f in arcpy.ListFields(parcel_fc)]
    if "PCL" not in fields:
        print(f"Field PCL does not exist in {parcel_fc}")
        return
    
    # Temporary output table for zonal stats
    temp_table = os.path.join("in_memory", f"zonal_stats_{year}")
    
    # Perform Zonal Statistics as Table
    print(f"Computing Zonal Statistics as Table for {year}...")
    arcpy.sa.ZonalStatisticsAsTable(parcel_fc, "PCL", raster_path, temp_table, "DATA", "MEAN")
    
    # Add a field to store the year
    arcpy.management.AddField(temp_table, "YEAR", "LONG")
    arcpy.management.CalculateField(temp_table, "YEAR", year)
    
    # Check the contents of the temporary table
    print("Contents of the temporary table:")
    with arcpy.da.SearchCursor(temp_table, ["PCL", "MEAN", "YEAR"]) as cursor:
        for row in cursor:
            print(f"Temporary Table Row: PCL={row[0]}, MEAN={row[1]}, YEAR={row[2]}")
    
    # Check if the parcel_db table already exists
    if arcpy.Exists(parcel_db):
        overwrite = input(f"The table {parcel_db} already exists. Do you want to overwrite it? (yes/no): ")
        if overwrite.lower() != 'yes':
            print(f"Skipping processing for the year {year}.")
            return
        else:
            arcpy.management.Delete(parcel_db)
            print(f"Deleted existing table {parcel_db}")

    # Create the parcel_dtw_stats table and add necessary fields
    arcpy.management.CreateTable(os.path.dirname(parcel_db), os.path.basename(parcel_db))
    required_fields = [
        {'name': 'PCL', 'type': 'TEXT'},
        {'name': 'MEAN', 'type': 'DOUBLE'},
        {'name': 'YEAR', 'type': 'LONG'}
    ]
    ensure_fields_exist(parcel_db, required_fields)
    
    # Append the results to the new parcel_dtw_stats table
    print(f"Appending results to {parcel_db}...")
    arcpy.management.Append(temp_table, parcel_db, "NO_TEST")
    
    # Export to CSV
    if os.path.exists(csv_path):
        overwrite = input(f"The CSV file {csv_path} already exists. Do you want to overwrite it? (yes/no): ")
        if overwrite.lower() == 'yes':
            os.remove(csv_path)
            arcpy.conversion.TableToTable(parcel_db, output_dir, f"parcel_dtw_stats_{year}.csv")
            print(f"Exported results to {csv_path}")
        else:
            print(f"Skipped exporting to {csv_path}")
    else:
        arcpy.conversion.TableToTable(parcel_db, output_dir, f"parcel_dtw_stats_{year}.csv")
        print(f"Exported results to {csv_path}")
    
    # Join the dtw_stats to the parcel polygons
    print(f"Joining {parcel_db} to {parcel_fc}...")
    arcpy.management.MakeFeatureLayer(parcel_fc, "parcel_layer")
    arcpy.management.AddJoin("parcel_layer", "PCL", parcel_db, "PCL")
    
    # Check if the new parcel layer already exists
    if arcpy.Exists(new_parcel_layer):
        overwrite = input(f"The feature class {new_parcel_layer} already exists. Do you want to overwrite it? (yes/no): ")
        if overwrite.lower() == 'yes':
            arcpy.management.Delete(new_parcel_layer)
            print(f"Deleted existing feature class {new_parcel_layer}")
        else:
            print(f"Skipping creation of {new_parcel_layer}")
            return
    
    # Copy the joined layer to a new feature class
    print(f"Creating new parcel layer: {new_parcel_layer}...")
    arcpy.management.CopyFeatures("parcel_layer", new_parcel_layer)
    
    print(f"Zonal statistics for year {year} appended to {parcel_db}, exported to {csv_path}, and new parcel layer created: {new_parcel_layer}.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Compute zonal statistics for kriged surface and append results to parcel database")
    parser.add_argument('--config', type=str, default='config.ini', help='Path to the configuration file')
    args = parser.parse_args()
    
    config = configparser.ConfigParser()
    config.read(args.config)
    
    base_path = os.path.abspath(config.get('settings', 'base_path'))
    parcel_fc = config.get('zonal_statistics', 'parcel_feature_class')
    
    # Determine the range of years to process
    years = config.get('settings', 'years')
    
    if '-' in years:
        start_year, end_year = map(int, years.split('-'))
        year_list = range(start_year, end_year + 1)
    elif ',' in years:
        year_list = [int(year) for year in years.split(',')]
    else:
        year_list = [int(years)]
    
    # Global Environment settings
    with arcpy.EnvManager(scratchWorkspace=os.path.join(base_path, "kriging.gdb"), workspace=os.path.join(base_path, "kriging.gdb")):
        for year in year_list:
            zonal_statistics(year, base_path, parcel_fc)
