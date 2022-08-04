import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import qcodes as qc

qc.initialise_or_create_database_at("D:/your_name/your_project.db")

dataframe = qc.load_by_run_spec(captured_run_id=943).to_pandas_dataframe()
s11_g = dataframe["s11_g"].values
s11_e = dataframe["s11_e"].values

plt.figure("g")
plt.hist2d(s11_g.real, s11_g.imag, bins=200, cmin=1, norm=mcolors.LogNorm())
plt.axis("scaled")
plt.xlabel("I")
plt.ylabel("Q")

plt.figure("e")
plt.hist2d(s11_e.real, s11_e.imag, bins=200, cmin=1, norm=mcolors.LogNorm())
plt.axis("scaled")
plt.xlabel("I")
plt.ylabel("Q")

plt.show()
