import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import folium_static
from shapely.geometry import Point, Polygon, LineString, MultiLineString
from shapely.geometry.base import BaseGeometry
from typing import List, Dict, Set, Tuple
from shapely import remove_repeated_points

def get_coordinates_with_index(geometry: BaseGeometry) -> List[Tuple[Tuple[float, float], int]]:
    """Extract all coordinates from a geometry with their index."""
    coords = []
    idx = 0

    if geometry.geom_type == 'Point':
        coords.append((tuple(geometry.coords[0])[:2], idx))

    elif geometry.geom_type in ['LineString', 'LinearRing']:
        unique_coords = list(geometry.coords)
        if unique_coords[0] == unique_coords[-1]:  
            unique_coords.pop()
        for coord in unique_coords:
            coords.append((tuple(coord)[:2], idx))
            idx += 1

    elif geometry.geom_type == 'Polygon':
        exterior_coords = list(geometry.exterior.coords)
        if exterior_coords[0] == exterior_coords[-1]:
            exterior_coords.pop()
        for coord in exterior_coords:
            coords.append((tuple(coord)[:2], idx))
            idx += 1

        for interior in geometry.interiors:
            interior_coords = list(interior.coords)
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

    seen = set()
    duplicates = set()
    for coord, _ in coords_with_index:
        if coord in seen:
            duplicates.add(coord)
        else:
            seen.add(coord)
    return duplicates

def plot_geometry(geometry: BaseGeometry, duplicates: Set[Tuple[float, float]], title: str = "") -> folium.Map:
    """Create a folium map with geometry and duplicate points highlighted."""
    centroid = geometry.centroid
    m = folium.Map(location=[centroid.y, centroid.x], zoom_start=15)
    
    # Add title to map
    if title:
        title_html = f'<h4 style="text-align:center;">{title}</h4>'
        m.get_root().html.add_child(folium.Element(title_html))
    
    gdf = gpd.GeoDataFrame(geometry=[geometry], crs="EPSG:4326")
    folium.GeoJson(gdf).add_to(m)

    # Plot duplicate vertices in red
    for coord in duplicates:
        folium.CircleMarker(location=[coord[1], coord[0]], radius=6, color='red', fill=True, fill_color='red',
                            fill_opacity=0.8, popup=f"Duplicate: {coord}").add_to(m)

    # Plot non-duplicate vertices in green
    for coord, _ in get_coordinates_with_index(geometry):
        if coord not in duplicates:
            folium.CircleMarker(location=[coord[1], coord[0]], radius=4, color='green', fill=True, fill_color='green',
                                fill_opacity=0.8, popup=f"Vertex: {coord}").add_to(m)

    return m

def remove_duplicates_from_geometry(geometry: BaseGeometry) -> BaseGeometry:
    """Remove duplicate vertices from a geometry using shapely.remove_repeated_points."""
    if geometry.geom_type == 'Polygon':
        exterior = LineString(geometry.exterior)
        interiors = [LineString(interior) for interior in geometry.interiors]
        exterior_cleaned = remove_repeated_points(exterior)
        interiors_cleaned = [remove_repeated_points(interior) for interior in interiors]
        return Polygon(exterior_cleaned, interiors_cleaned)

    elif geometry.geom_type == 'LineString':
        return remove_repeated_points(geometry)

    elif geometry.geom_type == 'MultiLineString':
        return MultiLineString([remove_repeated_points(line) for line in geometry.geoms])

    elif geometry.geom_type == 'MultiPolygon':
        return MultiPolygon([remove_duplicates_from_geometry(poly) for poly in geometry.geoms])

    else:
        return geometry

def main():
    st.title("GeoJSON Duplicate Vertices Detector")
    st.write("Upload a GeoJSON file to detect and remove duplicate vertices in geometries.")

    # Initialize session state
    if 'original_data' not in st.session_state:
        st.session_state.original_data = None
    if 'cleaned_data' not in st.session_state:
        st.session_state.cleaned_data = None

    uploaded_file = st.file_uploader("Choose a GeoJSON file", type=['geojson'])

    if uploaded_file is not None:
        try:
            # Only load the file if it's new or if there's no data loaded
            if st.session_state.original_data is None:
                gdf = gpd.read_file(uploaded_file)
                st.session_state.original_data = gdf
                st.session_state.cleaned_data = None  # Reset cleaned data when new file is uploaded
            else:
                gdf = st.session_state.original_data

            results = []
            total_duplicates = 0
            max_duplicates = 0
            min_duplicates = float('inf')

            with st.spinner("Processing features..."):
                progress_bar = st.progress(0)
                total_features = len(gdf)

                for idx, row in gdf.iterrows():
                    try:
                        duplicates = find_duplicate_vertices(row.geometry)

                        if duplicates:
                            properties = row.drop('geometry').to_dict()

                            result = {
                                'feature_id': idx,
                                'duplicate_count': len(duplicates),
                                'duplicate_coordinates': list(duplicates),
                                'geometry_type': row.geometry.geom_type,
                                'geometry': row.geometry,
                                **properties
                            }
                            results.append(result)

                            total_duplicates += len(duplicates)
                            max_duplicates = max(max_duplicates, len(duplicates))
                            min_duplicates = min(min_duplicates, len(duplicates))

                        progress = (idx + 1) / total_features
                        progress_bar.progress(progress)
                    except Exception as e:
                        st.warning(f"Skipping feature {idx} due to error: {str(e)}")
                        continue

            if results:
                st.header("Duplicate Vertices Analysis")

                df = pd.DataFrame(results)

                # Summary Section
                st.subheader("Summary of Duplicate Vertices")
                total_with_duplicates = len(df)
                percentage_with_duplicates = (total_with_duplicates / total_features) * 100 if total_features > 0 else 0

                summary_data = {
                    "Total Features": total_features,
                    "Total Features with Duplicates": total_with_duplicates,
                    "Total Duplicate Vertices": total_duplicates,
                    "Percentage of Features with Duplicates": f"{percentage_with_duplicates:.2f}%",
                    "Max Duplicate Vertices in a Feature": max_duplicates,
                    "Min Duplicate Vertices in a Feature": min_duplicates if min_duplicates != float('inf') else 0
                }

                summary_df = pd.DataFrame(summary_data.items(), columns=["Metric", "Value"])
                st.table(summary_df)

                # Remove Duplicates Button
                if st.button("Remove Duplicate Vertices from All Features") or st.session_state.cleaned_data is not None:
                    if st.session_state.cleaned_data is None:
                        with st.spinner("Removing duplicates from all features..."):
                            cleaned_results = []
                            for idx, row in df.iterrows():
                                cleaned_geometry = remove_duplicates_from_geometry(row['geometry'])
                                cleaned_duplicates = find_duplicate_vertices(cleaned_geometry)

                                cleaned_result = {
                                    'feature_id': row['feature_id'],
                                    'duplicate_count': len(cleaned_duplicates),
                                    'duplicate_coordinates': list(cleaned_duplicates),
                                    'geometry_type': cleaned_geometry.geom_type,
                                    'geometry': cleaned_geometry,
                                    **{k: v for k, v in row.items() if k not in ['geometry', 'duplicate_count', 'duplicate_coordinates']}
                                }
                                cleaned_results.append(cleaned_result)

                            # Store cleaned results in session state
                            st.session_state.cleaned_data = pd.DataFrame(cleaned_results)
                            st.success("Duplicate vertices removed from all features!")

                    # Feature Selection for Visualization
                    st.subheader("Select a feature to visualize")
                    selected_index = st.selectbox("Feature ID", df['feature_id'].tolist())

                    # Find selected rows from both original and cleaned data
                    original_row = df[df['feature_id'] == selected_index].iloc[0]
                    cleaned_row = st.session_state.cleaned_data[
                        st.session_state.cleaned_data['feature_id'] == selected_index
                    ].iloc[0]

                    # Create two columns for side-by-side map display
                    col1, col2 = st.columns(2)

                    with col1:
                        st.subheader("Original Geometry")
                        m1 = plot_geometry(
                            original_row['geometry'], 
                            set(original_row['duplicate_coordinates']),
                            "Original"
                        )
                        folium_static(m1)

                    with col2:
                        st.subheader("Cleaned Geometry")
                        m2 = plot_geometry(
                            cleaned_row['geometry'], 
                            set(cleaned_row['duplicate_coordinates']),
                            "After Cleaning"
                        )
                        folium_static(m2)

                    # Display comparison metrics
                    st.subheader("Comparison Metrics")
                    comparison_data = {
                        "Metric": ["Duplicate Vertices Count"],
                        "Original": [original_row['duplicate_count']],
                        "After Cleaning": [cleaned_row['duplicate_count']],
                        "Difference": [original_row['duplicate_count'] - cleaned_row['duplicate_count']]
                    }
                    st.table(pd.DataFrame(comparison_data))

                    # Allow downloading the cleaned GeoJSON
                    cleaned_gdf = gpd.GeoDataFrame(
                        st.session_state.cleaned_data.drop(columns=['duplicate_coordinates']), 
                        geometry='geometry'
                    )
                    cleaned_geojson = cleaned_gdf.to_json()
                    st.download_button(
                        "Download Cleaned GeoJSON",
                        cleaned_geojson,
                        "cleaned_geojson.geojson",
                        "application/geo+json"
                    )

                # Display DataFrame of duplicate vertices
                st.subheader("Duplicate Vertices Summary")
                coord_df = df[['feature_id', 'geometry_type', 'duplicate_count', 'duplicate_coordinates']]
                st.dataframe(coord_df)

                # Allow downloading the results as CSV
                csv = df.drop(columns=['geometry']).to_csv(index=False)
                st.download_button(
                    "Download results as CSV",
                    csv,
                    "duplicate_vertices_results.csv",
                    "text/csv"
                )

            else:
                st.success("No duplicate vertices found in the GeoJSON file!")

        except Exception as e:
            st.error(f"Error processing file: {str(e)}")

if __name__ == "__main__":
    main()
