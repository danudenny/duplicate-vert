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

def plot_geometry(geometry: BaseGeometry, duplicates: Set[Tuple[float, float]]):
    """Create a folium map with geometry and duplicate points highlighted."""
    centroid = geometry.centroid
    m = folium.Map(location=[centroid.y, centroid.x], zoom_start=15)
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
        # Convert Polygon exterior and interiors to LineString
        exterior = LineString(geometry.exterior)
        interiors = [LineString(interior) for interior in geometry.interiors]

        # Remove duplicate points from exterior and interiors
        exterior_cleaned = remove_repeated_points(exterior)
        interiors_cleaned = [remove_repeated_points(interior) for interior in interiors]

        # Convert back to Polygon
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
    st.write("Upload a GeoJSON file to detect duplicate vertices in geometries.")

    uploaded_file = st.file_uploader("Choose a GeoJSON file", type=['geojson'])

    if uploaded_file is not None:
        try:
            gdf = gpd.read_file(uploaded_file)

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

                # Drop geometry column for display
                display_df = df.drop(columns=['geometry', 'duplicate_coordinates'])

                # **Summary Section**
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

                # **Feature Selection for Visualization**
                st.subheader("Select a feature to visualize")
                selected_index = st.selectbox("Feature ID", df['feature_id'].tolist())

                # Find selected row
                selected_row = df[df['feature_id'] == selected_index].iloc[0]

                # Display folium map
                st.subheader(f"Feature {selected_index} Geometry Plot")
                m = plot_geometry(selected_row['geometry'], set(selected_row['duplicate_coordinates']))
                folium_static(m)

                # **Remove Duplicates Button**
                if st.button("Remove Duplicate Vertices"):
                    cleaned_geometry = remove_duplicates_from_geometry(selected_row['geometry'])
                    st.success("Duplicate vertices removed successfully!")

                    # Update the map with the cleaned geometry
                    st.subheader(f"Feature {selected_index} Cleaned Geometry Plot")
                    m_cleaned = plot_geometry(cleaned_geometry, set())
                    folium_static(m_cleaned)

                    # Update the DataFrame with the cleaned geometry
                    df.loc[df['feature_id'] == selected_index, 'geometry'] = cleaned_geometry
                    df.loc[df['feature_id'] == selected_index, 'duplicate_count'] = 0
                    df.loc[df['feature_id'] == selected_index, 'duplicate_coordinates'] = []

                    # Allow downloading the updated GeoJSON
                    updated_gdf = gpd.GeoDataFrame(df.drop(columns=['duplicate_coordinates']), geometry='geometry')
                    updated_geojson = updated_gdf.to_json()
                    st.download_button("Download Cleaned GeoJSON", updated_geojson, "cleaned_geojson.geojson", "application/geo+json")

                # Display DataFrame of duplicate vertices
                st.subheader("Duplicate Vertices Summary")
                coord_df = df[['feature_id', 'geometry_type', 'duplicate_count', 'duplicate_coordinates']]
                st.dataframe(coord_df)

                # Allow downloading the results as CSV
                csv = df.drop(columns=['geometry']).to_csv(index=False)
                st.download_button("Download results as CSV", csv, "duplicate_vertices_results.csv", "text/csv")

            else:
                st.success("No duplicate vertices found in the GeoJSON file!")

        except Exception as e:
            st.error(f"Error processing file: {str(e)}")

if __name__ == "__main__":
    main()
