# TODO:
argparser in order to launch directly from the terminal using
some important parameters scenario.json / calibration_year / source

In this tutorial, you will learn:
- How is organized the project?
- How to install an **environment** to **launch Res-IRF**, or a **detailed analysis of Res-IRF output**?
- How to launch Res-IRF, and what are the input/output of the model?
- How to launch *Res-IRF output analysis*?

# Use Res-IRF

## Possible use

Standard way to launch Res-IRF is in 2 steps (detailed explanations for each step are provided bellow):  
**Step 1: Launch Res-IRF main script.**  
The model will put all results in a folder in project/output.  
Folder name is by default ddmmyyyy_hhmm (launching date and hour) or can be change using script arguments --output (or -o).
Results are mainly .pkl or .csv file, and are not directly readable.  
NB: One file 'financials.csv' summarize important outputs.

**Step 2: Launch one of the Jupyter Notebook analysis tool**  
2 main 

### Launch Res-IRF main script.
Example: create your specific project/input/scenario.json

### Analyse Res-IRF output

#### Independent scenario
Jupyter notebook that takes in input an output folder from Res-IRF, and 

Tool: Jupyter notebook  
Kernel: Res-IRF kernel  
Code source: project/**user_interface.ipynb**  
Tool input: output folder from Res-IRF

#### Assess public policies
Tool: Jupyter notebook  
Kernel: Res-IRF kernel  
Code source: project/**assessment_policies.ipynb**
Tool input: project/output/folder_name

### Launch Res-IRF tutorials:
   - project/tutorials.ipynb



## First time installation
Follow the steps to easly use Res-IRF.

**Step 1**: Git **clone Res-IRF folder** in your computer.
   - Use your terminal and go to a location where you want to store the Res-IRF project.
   - `git clone https://github.com/lucas-vivier/Res-IRF.git`

**Step 2**: **Create a conda environment** from the environment.yml file:
   - The environment.yml file is in the Res-IRF folder.
   - Use the **terminal** and go to the Res-IRF folder stored on your computer.
   - Type: `conda env create -f environment.yml`

**Step 3**: **Activate the new environment**.
   - The first line of the yml file sets the new environment's name.
   - Type: `conda activate myenv`

**Step 4**: **Launch Res-IRF**
   - python main.py


# Additional information
## Conda environment

### Creating an environment from an environment.yml file
Tutorial comes from [this website](https://conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#creating-an-environment-from-an-environment-yml-file)
Use the terminal or an Anaconda Prompt for the following steps:

1. Create the environment from the environment.yml file:
`conda env create -f environment.yml`
The first line of the yml file sets the new environment's name.

2. Activate the new environment:
`conda activate myenv`

3. Verify that the new environment was installed correctly:
`conda env list`
You can also use `conda info --envs`.

### Sharing an environment
Tutorial comes from [this website](https://conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#creating-an-environment-from-an-environment-yml-file)
You may want to share your environment with someone else---for example, so they can re-create a test that you have done. To allow them to quickly reproduce your environment, with all of its packages and versions, give them a copy of your environment.yml file.
1. Activate the environment to export: `conda activate myenv`
   Replace myenv with the name of the environment
2. Export your active environment to a new file:
`conda env export > environment.yml`
3. Email or copy the exported `environment.yml` file to the other person.



## Jupyter Notebook

### Kernels

#### Create kernel
##### From conda environment
Tutorial comes from [this website](https://medium.com/@nrk25693/how-to-add-your-conda-environment-to-your-jupyter-notebook-in-just-4-steps-abeab8b8d084)  
**Step 1**: Create a Conda environment.
`conda create --name firstEnv`

**Step 2**: Activate the environment using the command as shown in the console. After you activate it, you can install any package you need in this environment.
`conda install library`

**Step 3**: Create Jupyter Kernel.
Now comes the step to set this conda environment on your jupyter notebook, to do so please install ipykernel.
`conda install -c anaconda ipykernel`
After installing this, just type:
`python -m ipykernel install --user --name=firstEnv`

**Step 4**: Just check your Jupyter Notebook, to see the shining firstEnv.

#### List kernels
`jupyter kernelspec list`
#### Remove kernel
`jupyter kernelspec remove <kernel-name>`