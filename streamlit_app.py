import streamlit as st
import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping
import numpy as np
from typing import Tuple, List, Dict

def get_coordinates_list(geometry: Dict) -> List[Tuple[float, float]]:
    """Extract all coordinates from a geometry as a list of tuples."""
    coords = []
    
    if geometry['type'] == 'Point':
        coords.append(tuple(geometry['coordinates']))
    elif geometry['type'] in ['LineString', 'MultiPoint']:
        coords.extend([tuple(c) for c in geometry['coordinates']])
    elif geometry['type'] in ['Polygon', 'MultiLineString']:
        for line in geometry['coordinates']:
            coords.extend([tuple(c) for c in line])
    elif geometry['type'] == 'MultiPolygon':
        for polygon in geometry['coordinates']:
            for line in polygon:
                coords.extend([tuple(c) for c in line])
    
    return coords

def find_duplicate_vertices(geometry: Dict) -> List[Tuple[float, float]]:
    """Find duplicate vertices in a geometry."""
    coords = get_coordinates_list(geometry)
    # Convert to numpy array for faster processing
    coords_array = np.array(coords)
    
    # Find duplicates using numpy
    unique_coords, counts = np.unique(coords_array, axis=0, return_counts=True)
    duplicate_mask = counts > 1
    duplicates = unique_coords[duplicate_mask].tolist()
    
    return [tuple(coord) for coord in duplicates]

def main():
    st.title("GeoJSON Duplicate Vertices Detector")
    st.write("Upload a GeoJSON file to detect duplicate vertices in geometries")
    
    # File uploader
    uploaded_file = st.file_uploader("Choose a GeoJSON file", type=['geojson'])
    
    if uploaded_file is not None:
        try:
            # Read GeoJSON
            gdf = gpd.read_file(uploaded_file)
            
            # Create a list to store results
            results = []
            
            # Process each feature
            for idx, row in gdf.iterrows():
                # Convert Shapely geometry to dictionary using mapping
                geom_dict = mapping(row.geometry)
                duplicates = find_duplicate_vertices(geom_dict)
                
                if duplicates:
                    # Get all properties from the feature
                    properties = row.drop('geometry').to_dict()
                    
                    # Add result with all properties
                    result = {
                        'feature_id': idx,
                        'duplicate_count': len(duplicates),
                        'duplicate_coordinates': duplicates,
                        **properties  # Include all other properties
                    }
                    results.append(result)
            
            if results:
                st.write(f"Found {len(results)} features with duplicate vertices")
                
                # Convert results to DataFrame
                df = pd.DataFrame(results)
                
                # Separate coordinate display
                coord_df = df[['feature_id', 'duplicate_count', 'duplicate_coordinates']]
                st.subheader("Duplicate Vertices Summary")
                st.dataframe(coord_df)
                
                # Display all properties
                if len(df.columns) > 3:  # If there are additional properties
                    st.subheader("Feature Properties")
                    property_df = df.drop(['duplicate_coordinates'], axis=1)
                    st.dataframe(property_df)
                
                # Add download button for results
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download results as CSV",
                    data=csv,
                    file_name="duplicate_vertices_results.csv",
                    mime="text/csv"
                )
                
                # Display map if coordinates are present
                if not gdf.empty:
                    st.subheader("Map View")
                    st.map(gdf)
            
            else:
                st.success("No duplicate vertices found in the GeoJSON file!")
                
            # Show original data properties
            st.subheader("Original Data Properties")
            properties_df = gdf.drop('geometry', axis=1)
            st.dataframe(properties_df)
            
        except Exception as e:
            st.error(f"Error processing file: {str(e)}")

if __name__ == "__main__":
    main()
