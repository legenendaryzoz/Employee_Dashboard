import pandas as pd
import plotly.express as px
import streamlit as st
from scipy import stats

st.set_page_config(page_title="Employee Dashboard", layout="wide")

BLUE = "#2a78d6"
ORANGE = "#eb6834"
GRAY = "#8a8880"
gender_colors = {"Female": ORANGE, "Male": BLUE}


@st.cache_data
def load_data():
    df = pd.read_excel("employee.xlsx")
    # last start date is 2014-12-25 so I'm using 1 Jan 2015 to calculate tenure
    df["tenure_years"] = (pd.Timestamp("2015-01-01") - df["start_date"]).dt.days / 365.25
    df["start_year"] = df["start_date"].dt.year
    # job titles like "Software Engineer III" -> level III
    df["level"] = df["job_title"].str.extract(r"\b(IV|I{1,3})$", expand=False).fillna("No level")
    df["region"] = "Region " + df["region_id"].astype(str)
    return df


def set_layout(fig, height=400):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=50, b=10), legend_title_text="")
    return fig


df = load_data()

# sidebar
st.sidebar.header("Filters")

dept_list = sorted(df["department"].unique())
dept_filter = st.sidebar.multiselect("Department", dept_list, default=dept_list)

gender_list = sorted(df["gender"].unique())
gender_filter = st.sidebar.multiselect("Gender", gender_list, default=gender_list)

region_list = sorted(df["region_id"].unique())
region_filter = st.sidebar.multiselect("Region", region_list, default=region_list)

min_year = int(df["start_year"].min())
max_year = int(df["start_year"].max())
year_filter = st.sidebar.slider("Start year", min_year, max_year, (min_year, max_year))

min_sal = int(df["salary"].min())
max_sal = int(df["salary"].max())
salary_filter = st.sidebar.slider("Salary", min_sal, max_sal, (min_sal, max_sal), step=1000)

data = df[
    (df["department"].isin(dept_filter))
    & (df["gender"].isin(gender_filter))
    & (df["region_id"].isin(region_filter))
    & (df["start_year"].between(year_filter[0], year_filter[1]))
    & (df["salary"].between(salary_filter[0], salary_filter[1]))
]

st.sidebar.write(f"{len(data)} out of {len(df)} employees selected")

st.title("Employee Dashboard")

if len(data) == 0:
    st.warning("No data for the selected filters")
    st.stop()

# KPIs
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Employees", len(data))
col2.metric("Median Salary", f"${data['salary'].median():,.0f}")
col3.metric("Average Salary", f"${data['salary'].mean():,.0f}")
col4.metric("Avg Tenure (years)", round(data["tenure_years"].mean(), 1))
col5.metric("Female %", f"{(data['gender'] == 'Female').mean() * 100:.0f}%")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Overview", "Salary", "Hiring", "Job Titles", "Data"])

with tab1:
    col1, col2 = st.columns(2)

    with col1:
        fig = px.histogram(data, x="salary", nbins=22, title="Salary Distribution",
                           color_discrete_sequence=[BLUE])
        fig.update_traces(marker_line_width=2, marker_line_color="white")
        fig.update_layout(xaxis_title="Salary", yaxis_title="Count", bargap=0)
        st.plotly_chart(set_layout(fig), width="stretch")

    with col2:
        dept_counts = data["department"].value_counts().sort_values()
        fig = px.bar(dept_counts, orientation="h", title="Employees per Department",
                     color_discrete_sequence=[BLUE])
        fig.update_layout(xaxis_title="Count", yaxis_title="", showlegend=False)
        st.plotly_chart(set_layout(fig, 500), width="stretch")

    col3, col4 = st.columns(2)

    with col3:
        gender_counts = data["gender"].value_counts().reset_index()
        fig = px.pie(gender_counts, names="gender", values="count", hole=0.5, title="Gender",
                     color="gender", color_discrete_map=gender_colors)
        st.plotly_chart(set_layout(fig), width="stretch")

    with col4:
        region_df = data.groupby("region").agg(employees=("id", "count"),
                                                avg_salary=("salary", "mean")).reset_index()
        fig = px.bar(region_df, x="region", y="employees", title="Employees per Region",
                     hover_data={"avg_salary": ":,.0f"}, color_discrete_sequence=[BLUE])
        fig.update_layout(xaxis_title="", yaxis_title="Count")
        st.plotly_chart(set_layout(fig), width="stretch")

with tab2:
    st.subheader("Salary by Department")

    # compare each department against everyone else
    # (multiply p by number of departments = bonferroni correction)
    n_depts = data["department"].nunique()
    sig_depts = []
    if n_depts > 1:
        for dept, group in data.groupby("department"):
            others = data[data["department"] != dept]["salary"]
            if len(group) > 2 and len(others) > 2:
                p = stats.ttest_ind(group["salary"], others, equal_var=False).pvalue
                if p * n_depts < 0.05:
                    sig_depts.append(dept)

    dept_order = data.groupby("department")["salary"].median().sort_values(ascending=False).index.tolist()
    plot_df = data.copy()
    plot_df["significant"] = plot_df["department"].apply(lambda d: "Yes" if d in sig_depts else "No")

    fig = px.box(plot_df, x="department", y="salary", color="significant",
                 category_orders={"department": dept_order},
                 color_discrete_map={"Yes": ORANGE, "No": BLUE})
    fig.add_hline(y=data["salary"].median(), line_dash="dash", line_color=GRAY,
                  annotation_text="Median")
    fig.update_layout(xaxis_title="", yaxis_title="Salary", boxmode="overlay")
    st.plotly_chart(set_layout(fig, 480), width="stretch")
    st.caption("Orange = department salary is significantly different from the rest (t-test with Bonferroni correction)")

    if n_depts > 1:
        groups = [g["salary"] for _, g in data.groupby("department") if len(g) > 1]
        kw_p = stats.kruskal(*groups).pvalue
        # eta squared = how much of the salary variation is explained by department
        mean_sal = data["salary"].mean()
        ss_between = sum(len(g) * (g.mean() - mean_sal) ** 2 for g in groups)
        ss_total = ((data["salary"] - mean_sal) ** 2).sum()

        col1, col2 = st.columns(2)
        col1.metric("Kruskal-Wallis p-value", round(kw_p, 3))
        col2.metric("Eta squared", f"{ss_between / ss_total * 100:.1f}%")

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Salary by Gender")
        fig = px.box(data, x="gender", y="salary", color="gender", color_discrete_map=gender_colors)
        fig.update_layout(xaxis_title="", yaxis_title="Salary", showlegend=False)
        st.plotly_chart(set_layout(fig, 380), width="stretch")

        male = data[data["gender"] == "Male"]["salary"]
        female = data[data["gender"] == "Female"]["salary"]
        if len(male) > 2 and len(female) > 2:
            p = stats.ttest_ind(male, female, equal_var=False).pvalue
            diff = female.mean() - male.mean()
            st.write(f"Difference (Female - Male): {diff:,.0f}, p-value = {p:.3f}")
            if p < 0.05:
                st.write("The difference is significant")
            else:
                st.write("The difference is not significant")

    with col2:
        st.subheader("Salary by Level")
        fig = px.box(data, x="level", y="salary", color_discrete_sequence=[BLUE],
                     category_orders={"level": ["I", "II", "III", "IV", "No level"]})
        fig.update_layout(xaxis_title="Level", yaxis_title="Salary")
        st.plotly_chart(set_layout(fig, 380), width="stretch")

        with_level = data[data["level"] != "No level"]
        if with_level["level"].nunique() > 1:
            p = stats.kruskal(*[g["salary"] for _, g in with_level.groupby("level")]).pvalue
            st.write(f"Kruskal-Wallis p-value (levels I to IV): {p:.3f}")

    st.divider()
    st.subheader("Salary vs Tenure")
    fig = px.scatter(data, x="tenure_years", y="salary", color="gender", opacity=0.55,
                     color_discrete_map=gender_colors, trendline="ols", trendline_scope="overall",
                     trendline_color_override=GRAY, hover_data=["last_name", "department", "job_title"])
    fig.update_layout(xaxis_title="Tenure (years)", yaxis_title="Salary")
    st.plotly_chart(set_layout(fig, 420), width="stretch")

    if len(data) > 2:
        r, p = stats.pearsonr(data["tenure_years"], data["salary"])
        st.write(f"Correlation: {r:.3f} (p-value = {p:.3f})")

with tab3:
    col1, col2 = st.columns(2)

    with col1:
        hires = data.groupby("start_year").size()
        hires = hires.reindex(range(year_filter[0], year_filter[1] + 1), fill_value=0)
        fig = px.bar(x=hires.index, y=hires.values, title="Hires per Year",
                     color_discrete_sequence=[BLUE])
        fig.update_layout(xaxis_title="Year", yaxis_title="Hires")
        st.plotly_chart(set_layout(fig), width="stretch")

    with col2:
        yearly = data.groupby("start_year")["salary"].median().reset_index()
        fig = px.line(yearly, x="start_year", y="salary", markers=True,
                      title="Median Salary by Start Year", color_discrete_sequence=[BLUE])
        fig.update_layout(xaxis_title="Year", yaxis_title="Median Salary")
        st.plotly_chart(set_layout(fig), width="stretch")

    st.subheader("Gender % by Department")
    gender_pct = pd.crosstab(data["department"], data["gender"], normalize="index") * 100
    gender_pct_long = gender_pct.reset_index().melt(id_vars="department", var_name="gender",
                                                    value_name="percent")
    fig = px.bar(gender_pct_long, y="department", x="percent", color="gender", orientation="h",
                 color_discrete_map=gender_colors,
                 category_orders={"department": gender_pct.sort_values(gender_pct.columns[0]).index.tolist()})
    fig.add_vline(x=50, line_dash="dash", line_color=GRAY)
    fig.update_layout(xaxis_title="%", yaxis_title="")
    st.plotly_chart(set_layout(fig, 550), width="stretch")

    st.subheader("Average Salary by Department and Region")
    pivot = data.pivot_table(index="department", columns="region", values="salary", aggfunc="mean")
    fig = px.imshow(pivot, color_continuous_scale="Blues", aspect="auto", text_auto=".2s")
    fig.update_layout(xaxis_title="", yaxis_title="")
    st.plotly_chart(set_layout(fig, 550), width="stretch")
    st.caption("Note: some of these cells only have a few employees")

with tab4:
    # a lot of job titles only have 1 or 2 people so filter them out
    min_count = st.slider("Minimum number of employees per job title", 1, 15, 10)

    title_counts = data["job_title"].value_counts()
    titles_to_keep = title_counts[title_counts >= min_count].index

    titles = data[data["job_title"].isin(titles_to_keep)].groupby("job_title").agg(
        employees=("id", "count"),
        median_salary=("salary", "median"),
        mean_salary=("salary", "mean"),
    ).sort_values("median_salary")

    st.write(f"{len(titles)} job titles have at least {min_count} employees")

    if len(titles) > 0:
        top_titles = titles.tail(25)
        fig = px.bar(top_titles, x="median_salary", y=top_titles.index, orientation="h",
                     title="Median Salary by Job Title (top 25)", color_discrete_sequence=[BLUE],
                     hover_data=["employees"])
        fig.update_layout(xaxis_title="Median Salary", yaxis_title="")
        st.plotly_chart(set_layout(fig, 650), width="stretch")
        st.dataframe(titles.sort_values("median_salary", ascending=False).round(0), width="stretch")

with tab5:
    search = st.text_input("Search (name, email or job title)")

    table = data
    if search:
        table = data[
            data["last_name"].str.contains(search, case=False)
            | data["email"].str.contains(search, case=False)
            | data["job_title"].str.contains(search, case=False)
        ]

    columns = ["id", "last_name", "email", "gender", "department", "job_title", "level",
               "region_id", "start_date", "tenure_years", "salary"]
    st.dataframe(table[columns].round(1), width="stretch", hide_index=True)

    csv = table[columns].to_csv(index=False)
    st.download_button("Download CSV", csv, file_name="employees.csv", mime="text/csv")
