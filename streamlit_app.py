from shapely.geometry import Polygon, LineString, MultiLineString, MultiPolygon
from shapely.ops import remove_repeated_points

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
    st.write("Upload a GeoJSON file to detect and remove duplicate vertices in geometries.")

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

                # **Remove Duplicates Button for All Features**
                if st.button("Remove Duplicate Vertices from All Features"):
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

                        # Update the DataFrame with cleaned results
                        df = pd.DataFrame(cleaned_results)
                        st.success("Duplicate vertices removed from all features!")

                        # Update the summary
                        total_duplicates = df['duplicate_count'].sum()
                        max_duplicates = df['duplicate_count'].max()
                        min_duplicates = df['duplicate_count'].min()
                        total_with_duplicates = len(df[df['duplicate_count'] > 0])
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

                        # Allow downloading the cleaned GeoJSON
                        cleaned_gdf = gpd.GeoDataFrame(df.drop(columns=['duplicate_coordinates']), geometry='geometry')
                        cleaned_geojson = cleaned_gdf.to_json()
                        st.download_button("Download Cleaned GeoJSON", cleaned_geojson, "cleaned_geojson.geojson", "application/geo+json")

                # **Feature Selection for Visualization**
                st.subheader("Select a feature to visualize")
                selected_index = st.selectbox("Feature ID", df['feature_id'].tolist())

                # Find selected row
                selected_row = df[df['feature_id'] == selected_index].iloc[0]

                # Display folium map
                st.subheader(f"Feature {selected_index} Geometry Plot")
                m = plot_geometry(selected_row['geometry'], set(selected_row['duplicate_coordinates']))
                folium_static(m)

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
