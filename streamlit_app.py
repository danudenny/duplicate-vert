import streamlit as st
import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping, Point
from shapely.strtree import STRtree
import numpy as np
from typing import Tuple, List, Dict, Set
from shapely.geometry.base import BaseGeometry

def get_coordinates_with_index(geometry: BaseGeometry) -> List[Tuple[Tuple[float, float], int]]:
    """Extract all coordinates from a geometry with their index."""
    coords = []
    coords_set = set()  # To track unique coordinates
    idx = 0
    
    # Get coordinates based on geometry type
    if hasattr(geometry, 'coords'):
        # Point, LineString
        for coord in geometry.coords:
            coord_tuple = tuple(coord)[:2]  # Take only x,y coordinates
            if coord_tuple not in coords_set:
                coords.append((coord_tuple, idx))
                coords_set.add(coord_tuple)
            idx += 1
    elif hasattr(geometry, 'geoms'):
        # MultiPoint, MultiLineString, MultiPolygon
        for geom in geometry.geoms:
            for coord in geom.coords:
                coord_tuple = tuple(coord)[:2]
                if coord_tuple not in coords_set:
                    coords.append((coord_tuple, idx))
                    coords_set.add(coord_tuple)
                idx += 1
    elif hasattr(geometry, 'exterior'):
        # Polygon
        for coord in geometry.exterior.coords:
            coord_tuple = tuple(coord)[:2]
            if coord_tuple not in coords_set:
                coords.append((coord_tuple, idx))
                coords_set.add(coord_tuple)
            idx += 1
        for interior in geometry.interiors:
            for coord in interior.coords:
                coord_tuple = tuple(coord)[:2]
                if coord_tuple not in coords_set:
                    coords.append((coord_tuple, idx))
                    coords_set.add(coord_tuple)
                idx += 1
    
    return coords

def find_duplicate_vertices_with_strtree(geometry: BaseGeometry, tolerance: float = 1e-8) -> Set[Tuple[float, float]]:
    """Find duplicate vertices in a geometry using STRtree for faster processing."""
    coords_with_index = get_coordinates_with_index(geometry)
    
    if not coords_with_index:
        return set()
    
    # Create points for STRtree
    points = [Point(coord[0]) for coord in coords_with_index]
    tree = STRtree(points)
    
    duplicates = set()
    processed = set()
    
    for i, (coord, idx) in enumerate(coords_with_index):
        if coord in processed:
            continue
            
        point = points[i]
        # Query nearby points
        nearby_idxs = tree.query(point.buffer(tolerance))
        
        # Count occurrences
        nearby_coords = set()
        for j in nearby_idxs:
            if j != i:  # Skip self
                nearby_coord = coords_with_index[j][0]
                # Check if truly duplicate (within tolerance)
                dx = abs(coord[0] - nearby_coord[0])
                dy = abs(coord[1] - nearby_coord[1])
                if dx <= tolerance and dy <= tolerance:
                    nearby_coords.add(coord)
        
        if nearby_coords:
            duplicates.update(nearby_coords)
        
        processed.add(coord)
    
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
        duplicate_percentage = (len(results) / len(gdf) * 100) if len(gdf) > 0 else 0
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
    
    # Add tolerance parameter
    tolerance = st.slider(
        "Coordinate matching tolerance (decimal degrees)",
        min_value=1e-10,
        max_value=1e-6,
        value=1e-8,
        format="%.0e",
        help="Vertices within this distance will be considered duplicates"
    )
    
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
                    # Find duplicates using STRtree
                    duplicates = find_duplicate_vertices_with_strtree(row.geometry, tolerance)
                    
                    if duplicates:
                        # Get all properties from the feature
                        properties = row.drop('geometry').to_dict()
                        
                        # Add result with all properties
                        result = {
                            'feature_id': idx,
                            'duplicate_count': len(duplicates),
                            'duplicate_coordinates': list(duplicates),
                            'geometry_type': row.geometry.type,
                            **properties  # Include all other properties
                        }
                        results.append(result)
                    
                    # Update progress
                    progress = (idx + 1) / total_features
                    progress_bar.progress(progress)
            
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
                
                # Display map if coordinates are present
                if not gdf.empty:
                    st.subheader("Map View")
                    st.map(gdf)
            
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
