import streamlit as st
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from typing import List, Dict, Set, Tuple
from shapely.geometry.base import BaseGeometry

def get_coordinates_with_index(geometry: BaseGeometry) -> List[Tuple[Tuple[float, float], int]]:
    """Extract all coordinates from a geometry with their index, excluding duplicate start-end for closed geometries."""
    coords = []
    idx = 0
    
    if geometry.geom_type == 'Point':
        coords.append((tuple(geometry.coords[0])[:2], idx))
    
    elif geometry.geom_type in ['LineString', 'LinearRing']:
        unique_coords = list(geometry.coords)
        
        # Remove last coordinate if it is the same as the first (closed ring)
        if geometry.geom_type == 'LinearRing' or (geometry.geom_type == 'LineString' and unique_coords[0] == unique_coords[-1]):
            unique_coords.pop()
        
        for coord in unique_coords:
            coords.append((tuple(coord)[:2], idx))
            idx += 1
    
    elif geometry.geom_type == 'Polygon':
        exterior_coords = list(geometry.exterior.coords)
        
        # Remove last coordinate if it is the same as the first (closed ring)
        if exterior_coords[0] == exterior_coords[-1]:
            exterior_coords.pop()
        
        for coord in exterior_coords:
            coords.append((tuple(coord)[:2], idx))
            idx += 1
        
        for interior in geometry.interiors:
            interior_coords = list(interior.coords)
            
            # Remove last coordinate if it is the same as the first (closed ring)
            if interior_coords[0] == interior_coords[-1]:
                interior_coords.pop()
            
            for coord in interior_coords:
                coords.append((tuple(coord)[:2], idx))
                idx += 1
    
    elif geometry.geom_type in ['MultiPoint', 'MultiLineString', 'MultiPolygon']:
        for part in geometry.geoms:
            part_coords = get_coordinates_with_index(part)
            coords.extend(part_coords)
            idx += len(part_coords)
    
    return coords


def find_duplicate_vertices(geometry: BaseGeometry) -> Set[Tuple[float, float]]:
    """Find duplicate vertices in a geometry using exact coordinate matching."""
    coords_with_index = get_coordinates_with_index(geometry)
    
    if not coords_with_index:
        return set()
    
    # Track seen coordinates and duplicates
    seen = set()
    duplicates = set()
    
    for coord, _ in coords_with_index:
        if coord in seen:
            duplicates.add(coord)
        else:
            seen.add(coord)
    
    return duplicates

def display_data_stats(gdf: gpd.GeoDataFrame, results: List[Dict]):
    """Display statistics about the uploaded data."""
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label="Total Features",
            value=len(gdf),
            help="Total number of features in the uploaded file"
        )
    
    with col2:
        st.metric(
            label="Features with Duplicates",
            value=len(results),
            help="Number of features that contain duplicate vertices"
        )
    
    with col3:
        duplicate_percentage = len(results) / len(gdf) * 100 if len(gdf) > 0 else 0
        st.metric(
            label="Percentage with Duplicates",
            value=f"{duplicate_percentage:.1f}%",
            help="Percentage of features containing duplicate vertices"
        )
    
    # Geometry type distribution
    st.subheader("Geometry Type Distribution")
    geometry_types = gdf.geometry.type.value_counts()
    geometry_df = pd.DataFrame({
        'Geometry Type': geometry_types.index,
        'Count': geometry_types.values
    })
    st.dataframe(geometry_df, hide_index=True)

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
            with st.spinner("Processing features..."):
                progress_bar = st.progress(0)
                total_features = len(gdf)
                
                for idx, row in gdf.iterrows():
                    try:
                        # Find duplicates using exact matching
                        duplicates = find_duplicate_vertices(row.geometry)
                        
                        if duplicates:
                            # Get all properties from the feature
                            properties = row.drop('geometry').to_dict()
                            
                            # Add result with all properties
                            result = {
                                'feature_id': idx,
                                'duplicate_count': len(duplicates),
                                'duplicate_coordinates': list(duplicates),
                                'geometry_type': row.geometry.geom_type,
                                **properties  # Include all other properties
                            }
                            results.append(result)
                        
                        # Update progress
                        progress = (idx + 1) / total_features
                        progress_bar.progress(progress)
                    except Exception as e:
                        st.warning(f"Skipping feature {idx} due to error: {str(e)}")
                        continue
            
            # Display data statistics
            st.header("Data Summary")
            display_data_stats(gdf, results)
            
            if results:
                st.header("Duplicate Vertices Analysis")
                
                # Convert results to DataFrame
                df = pd.DataFrame(results)
                
                # Separate coordinate display
                coord_df = df[['feature_id', 'geometry_type', 'duplicate_count', 'duplicate_coordinates']]
                st.subheader("Duplicate Vertices Summary")
                st.dataframe(coord_df)
                
                # Display all properties
                if len(df.columns) > 4:  # If there are additional properties
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
            
            else:
                st.success("No duplicate vertices found in the GeoJSON file!")
                
            # Show original data properties
            st.header("Original Data Properties")
            properties_df = gdf.drop('geometry', axis=1)
            st.dataframe(properties_df)
            
        except Exception as e:
            st.error(f"Error processing file: {str(e)}")

if __name__ == "__main__":
    main()
